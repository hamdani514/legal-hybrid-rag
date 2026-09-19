from datetime import datetime, timezone
import hashlib
import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from loguru import logger

from app.database import db
from app.ingestion.detector import detect_pdf_type
from app.ingestion.extractor import extract
from app.ingestion.parser import parse_sections
from app.vectorstore.chroma_store import chroma_store
from app.services.email_service import send_contact_notification, send_contact_acknowledgement

router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

CONNECTION_DIR = Path(__file__).resolve().parents[1] / "connection"
CONNECTION_DIR.mkdir(parents=True, exist_ok=True)


ACTIVE_INGESTION_TASKS: dict[str, asyncio.Task] = {}


async def run_extraction(pdf_id: str, pdf_path: str, detected_type: str) -> None:
    try:
        if db.jobs is None or db.documents is None:
            logger.error(f"[{pdf_id}] Skipping extraction: database is not connected")
            return

        async def is_cancelled() -> bool:
            if pdf_id not in ACTIVE_INGESTION_TASKS:
                return True
            job = await db.jobs.find_one({"job_id": pdf_id})
            return job is None

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled before starting extraction.")
            return

        logger.info(f"[{pdf_id}] Extraction started")
        await db.jobs.update_one(
            {"job_id": pdf_id},
            {"$set": {"status": "extracting"}},
        )

        text = extract(pdf_path=pdf_path, pdf_id=pdf_id, detected_type=detected_type)
        
        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled after text extraction.")
            return

        now = datetime.now(timezone.utc)
        await db.jobs.update_one(
            {"job_id": pdf_id},
            {"$set": {"status": "extracted", "char_count": len(text), "extracted_at": now}},
        )
        await db.documents.update_one(
            {"pdf_id": pdf_id},
            {"$set": {"status": "extracted"}},
        )
        logger.info(f"[{pdf_id}] Extraction completed (chars={len(text)})")

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled before parsing.")
            return

        await db.jobs.update_one(
            {"job_id": pdf_id},
            {"$set": {"status": "parsing"}},
        )
        logger.info(f"[{pdf_id}] Parsing started")

        final = await asyncio.wait_for(
            parse_sections(pdf_id=pdf_id, extracted_text=text),
            timeout=600,
        )

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled after parsing.")
            for suffix in ["_sections.json", "_summary.md"]:
                f_path = UPLOADS_DIR / f"{pdf_id}{suffix}"
                if f_path.exists():
                    f_path.unlink()
            return

        parsed_at = datetime.now(timezone.utc)
        await db.jobs.update_one(
            {"job_id": pdf_id},
            {"$set": {"status": "parsed", "parsed_at": parsed_at}},
        )
        await db.documents.update_one(
            {"pdf_id": pdf_id},
            {"$set": {"status": "parsed"}},
        )
        logger.info(f"[{pdf_id}] Parsing completed")

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled before building tree.")
            return

        # Build and save hierarchical tree in MongoDB
        from app.ingestion.tree_builder import build_and_save_tree
        await build_and_save_tree(pdf_id, final)

        if await is_cancelled():
            logger.info(f"[{pdf_id}] Ingestion cancelled before embedding generation.")
            return

        # Auto-generate embeddings and store in ChromaDB + JSON mapping
        from app.ingestion.embedding_pipeline import run_embedding_pipeline
        logger.info(f"[{pdf_id}] Tree created. Running embedding generation pipeline...")
        await run_embedding_pipeline(pdf_id=pdf_id, force_regenerate=True)
        logger.info(f"[{pdf_id}] Embedding generation pipeline completed successfully.")

    except asyncio.CancelledError:
        logger.warning(f"[{pdf_id}] Ingestion task was explicitly cancelled by user.")
        for suffix in [".pdf", ".txt", "_sections.json", "_summary.md"]:
            f_path = UPLOADS_DIR / f"{pdf_id}{suffix}"
            if f_path.exists():
                try:
                    f_path.unlink()
                except Exception:
                    pass
    except asyncio.TimeoutError:
        failed_at = datetime.now(timezone.utc)
        error_message = "Parsing timed out after 600 seconds."
        await db.jobs.update_one(
            {"job_id": pdf_id},
            {"$set": {"status": "parse_failed", "error": error_message, "failed_at": failed_at}},
        )
        await db.documents.update_one(
            {"pdf_id": pdf_id},
            {"$set": {"status": "failed"}},
        )
        logger.error(f"[{pdf_id}] {error_message}")
    except Exception as e:
        now = datetime.now(timezone.utc)
        await db.jobs.update_one(
            {"job_id": pdf_id},
            {"$set": {"status": "parse_failed", "error": str(e), "failed_at": now}},
        )
        await db.documents.update_one(
            {"pdf_id": pdf_id},
            {"$set": {"status": "failed"}},
        )
        logger.exception(f"[{pdf_id}] Ingestion failed: {e}")
    finally:
        ACTIVE_INGESTION_TASKS.pop(pdf_id, None)


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    original_filename = file.filename or "uploaded.pdf"
    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    pdf_id = str(uuid4())
    job_id = pdf_id
    filename = original_filename
    saved_path = UPLOADS_DIR / f"{pdf_id}.pdf"

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    if db.jobs is None or db.documents is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    existing_doc = await db.documents.find_one(
        {"file_hash": file_hash},
        {"_id": 0, "pdf_id": 1, "filename": 1, "status": 1},
    )
    if existing_doc:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate PDF detected. Already uploaded as '{existing_doc.get('filename', 'unknown')}'.",
        )

    saved_path.write_bytes(file_bytes)

    from app.ingestion.validator import validate_judgment
    is_valid, validation_msg = validate_judgment(str(saved_path))
    if not is_valid:
        if saved_path.exists():
            saved_path.unlink()
        raise HTTPException(status_code=400, detail=validation_msg)

    detected_type = detect_pdf_type(str(saved_path))
    now = datetime.now(timezone.utc)

    await db.jobs.insert_one(
        {
            "job_id": job_id,
            "pdf_id": pdf_id,
            "filename": filename,
            "detected_type": detected_type,
            "status": "uploaded",
            "created_at": now,
            "file_hash": file_hash,
        }
    )

    await db.documents.insert_one(
        {
            "pdf_id": pdf_id,
            "filename": filename,
            "detected_type": detected_type,
            "status": "uploaded",
            "upload_date": now,
            "total_nodes": 0,
            "file_hash": file_hash,
        }
    )
    task = asyncio.create_task(run_extraction(pdf_id, str(saved_path), detected_type))
    ACTIVE_INGESTION_TASKS[pdf_id] = task
    ACTIVE_INGESTION_TASKS[job_id] = task
    logger.info(f"[{pdf_id}] Upload saved and extraction task launched")

    return {
        "pdf_id": pdf_id,
        "filename": filename,
        "detected_type": detected_type,
        "job_id": job_id,
        "status": "uploaded",
        "message": "PDF received. Use job_id to track progress.",
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if db.jobs is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job


@router.get("/jobs")
async def list_jobs():
    if db.jobs is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    cursor = db.jobs.find({}, {"_id": 0}).sort("created_at", -1)
    jobs = await cursor.to_list(length=None)
    return {"jobs": jobs}


@router.get("/extracted/{pdf_id}")
async def get_extracted(pdf_id: str):
    txt_path = UPLOADS_DIR / f"{pdf_id}.txt"
    if not txt_path.exists():
        raise HTTPException(status_code=404, detail="Extracted text not found.")

    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    return {"pdf_id": pdf_id, "char_count": len(text), "preview": text[:500]}


@router.get("/parsed/{pdf_id}")
async def get_parsed(pdf_id: str):
    parsed_path = UPLOADS_DIR / f"{pdf_id}_sections.json"
    if not parsed_path.exists():
        raise HTTPException(status_code=404, detail="Parsed sections not found.")

    import json

    parsed = json.loads(parsed_path.read_text(encoding="utf-8", errors="ignore"))
    sections = []
    for section in parsed.get("sections", []):
        text = section.get("text", "") or ""
        sections.append(
            {
                "section_type": section.get("section_type"),
                "heading_found": section.get("heading_found"),
                "char_count": len(text),
                "confidence": section.get("confidence", 0.0),
                "preview": text[:300],
            }
        )

    return {
        "pdf_id": pdf_id,
        "parse_mode": parsed.get("parse_mode", "unknown"),
        "context_heading": parsed.get("context_heading", ""),
        "context_summary": parsed.get("context_summary", ""),
        "sections": sections,
    }


@router.get("/tree/{pdf_id}")
async def get_tree(pdf_id: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    tree = await db.database.document_trees.find_one({"pdf_id": pdf_id}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Tree structure not found for this PDF.")

    return tree


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    if db.jobs is None or db.documents is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    # Try finding job by job_id or pdf_id
    job = await db.jobs.find_one({"$or": [{"job_id": job_id}, {"pdf_id": job_id}]}, {"_id": 0, "pdf_id": 1, "job_id": 1})
    doc = None
    if not job:
        doc = await db.documents.find_one({"$or": [{"pdf_id": job_id}, {"job_id": job_id}]}, {"_id": 0, "pdf_id": 1, "job_id": 1})

    if not job and not doc:
        pdf_id = job_id
        actual_job_id = job_id
    else:
        pdf_id = (job or doc).get("pdf_id") or job_id
        actual_job_id = (job or doc).get("job_id") or job_id

    # 0. Cancel active background task immediately if running
    for key in [job_id, pdf_id, actual_job_id]:
        if key and key in ACTIVE_INGESTION_TASKS:
            t = ACTIVE_INGESTION_TASKS.pop(key, None)
            if t and not t.done():
                logger.info(f"Explicitly cancelling running extraction task for {key}")
                t.cancel()

    # 1. MongoDB Collections Cleanup
    deleted_counts = {}
    try:
        res_docs = await db.documents.delete_many({"$or": [{"pdf_id": pdf_id}, {"job_id": actual_job_id}]})
        deleted_counts["documents"] = res_docs.deleted_count

        res_jobs = await db.jobs.delete_many({"$or": [{"pdf_id": pdf_id}, {"job_id": actual_job_id}]})
        deleted_counts["jobs"] = res_jobs.deleted_count

        # Cleanup nodes collection
        deleted_nodes_count = 0
        if db.nodes is not None:
            res_nodes = await db.nodes.delete_many({"$or": [{"pdf_id": pdf_id}, {"file_id": pdf_id}]})
            deleted_nodes_count += res_nodes.deleted_count
        
        if db.database is not None:
            if hasattr(db.database, "nodes"):
                res_db_nodes = await db.database.nodes.delete_many({"$or": [{"pdf_id": pdf_id}, {"file_id": pdf_id}]})
                deleted_nodes_count += res_db_nodes.deleted_count
            # Cleanup document trees collection
            res_trees = await db.database.document_trees.delete_many({"$or": [{"pdf_id": pdf_id}, {"file_id": pdf_id}]})
            deleted_counts["document_trees"] = res_trees.deleted_count
            # Cleanup embedding mappings collection
            res_mappings = await db.database.embedding_mappings.delete_many({"$or": [{"file_id": pdf_id}, {"pdf_id": pdf_id}, {"doc_id": pdf_id}]})
            deleted_counts["embedding_mappings"] = res_mappings.deleted_count
            
        deleted_counts["nodes"] = deleted_nodes_count
        logger.info(f"MongoDB records purged for {pdf_id}: {deleted_counts}")
    except Exception as e:
        logger.error(f"Error purging MongoDB collections for {pdf_id}: {e}")

    # 2. ChromaDB Vectors Cleanup
    try:
        chroma_store.delete_by_file_id(pdf_id)
        logger.info(f"ChromaDB vectors purged for file_id: {pdf_id}")
    except Exception as e:
        logger.warning(f"Notice during ChromaDB vector purge for {pdf_id}: {e}")

    # 3. Connection JSON Files Cleanup (backend/app/connection)
    try:
        if CONNECTION_DIR.exists():
            for conn_file in list(CONNECTION_DIR.glob(f"{pdf_id}*")):
                try:
                    conn_file.unlink()
                    logger.info(f"Deleted connection file: {conn_file.name}")
                except Exception as ex:
                    logger.error(f"Error removing connection file {conn_file}: {ex}")
    except Exception as e:
        logger.error(f"Error cleaning connection files for {pdf_id}: {e}")

    # 4. Uploads Files Cleanup (backend/uploads)
    try:
        if UPLOADS_DIR.exists():
            for upload_file in list(UPLOADS_DIR.glob(f"{pdf_id}*")):
                try:
                    upload_file.unlink()
                    logger.info(f"Deleted upload file: {upload_file.name}")
                except Exception as ex:
                    logger.error(f"Error removing upload file {upload_file}: {ex}")
    except Exception as e:
        logger.error(f"Error cleaning upload files for {pdf_id}: {e}")

    return {
        "message": "Judgment, node tree, Chroma vectors, connection mappings, and all associated files deleted successfully.",
        "job_id": actual_job_id,
        "pdf_id": pdf_id,
    }


@router.get("/status")
async def admin_status():
    if db.documents is None or db.jobs is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    total_documents = await db.documents.count_documents({})

    statuses = ["complete", "parsed", "failed", "uploaded", "processing"]
    by_status = {}
    for status in statuses:
        by_status[status] = await db.documents.count_documents({"status": status})

    cursor = db.jobs.find({}, {"_id": 0}).sort("created_at", -1)
    all_jobs = await cursor.to_list(length=None)

    return {
        "total_documents": total_documents,
        "by_status": by_status,
        "recent_jobs": all_jobs[:5],
        "all_jobs": all_jobs,
    }


# ----------------------------
# User Management Integration
# ----------------------------
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: str
    name: str
    org: str
    plan: str
    password: str
    dob: str
    gender: str = "Male"
    phone_no: str = ""
    created_at: str = None


class UserUpdate(BaseModel):
    username: str
    email: str
    name: str
    org: str
    plan: str
    password: str
    dob: str
    gender: str = "Male"
    phone_no: str = ""


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one capital letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one small letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")
    if not re.search(r"[!@#$%^&*()_+\[\]{}|;:',.<>?/`~\"\\-]", password):
        raise ValueError("Password must contain at least one special character.")


def validate_email_domain(email: str) -> None:
    if not email.strip().lower().endswith("@gmail.com"):
        raise ValueError("Email must be a @gmail.com domain.")


def validate_age_limit(dob_str: str, reg_date: datetime) -> None:
    try:
        dob_date = datetime.strptime(dob_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("DOB must be in YYYY-MM-DD format.")
    
    reg_date_val = reg_date.date() if isinstance(reg_date, datetime) else reg_date
    dob_date_val = dob_date.date() if isinstance(dob_date, datetime) else dob_date
    
    age = reg_date_val.year - dob_date_val.year - ((reg_date_val.month, reg_date_val.day) < (dob_date_val.month, dob_date_val.day))
    if age < 16:
        raise ValueError("User must be older than 16 years from the registration date.")


async def validate_human_name(username: str) -> bool:
    from app.ingestion.parser import call_ollama, clean_json_response
    import json
    
    base_name = re.sub(r'[\d_.-]', '', username).strip()
    if not base_name:
        return False
        
    prompt = (
        f"Answer YES or NO if the following string is a reasonable human name or is based on a human name:\n"
        f"String: {base_name}\n"
        f"If the string represents an animal (e.g. cat, dog, lion), a non-living object (e.g. table, chair, window, computer), "
        f"a general dictionary noun/verb (e.g. run, beautiful, system), or random gibberish, answer NO.\n"
        f"Format your response as a JSON object with keys:\n"
        f"{{\"is_human_name\": true/false, \"reason\": \"explanation\"}}"
    )
    system = "You are a database validator helper. Respond in JSON only."
    try:
        raw = await call_ollama(prompt, system)
        cleaned = clean_json_response(raw)
        parsed = json.loads(cleaned)
        return bool(parsed.get("is_human_name", False))
    except Exception as e:
        logger.error(f"Ollama human name validation failed: {e}")
        obvious_no = {"table", "chair", "desk", "computer", "phone", "window", "door", "car", "dog", "cat", "bird", "fish", "lion", "tiger", "cow", "sheep"}
        if base_name.lower() in obvious_no:
            return False
        return True


# Import re for regex validation
import re

@router.get("/users")
async def get_users():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    cursor = db.database.users.find({}).sort("created_at", -1)
    users = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if "created_at" in doc and doc["created_at"]:
            if isinstance(doc["created_at"], datetime):
                doc["created_at"] = doc["created_at"].isoformat()
        users.append(doc)
    
    total_users = len(users)
    pro_users = sum(1 for u in users if u.get("plan") == "Pro")
    standard_users = sum(1 for u in users if u.get("plan") == "Standard")
    
    return {
        "users": users,
        "total_users": total_users,
        "pro_users": pro_users,
        "standard_users": standard_users
    }


@router.post("/users")
async def create_user(user: UserCreate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    # 1. Validate Email
    try:
        validate_email_domain(user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 2. Validate Password
    try:
        validate_password_strength(user.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 3. Validate DOB
    now = datetime.now(timezone.utc)
    if user.created_at:
        try:
            client_time_str = user.created_at.replace("Z", "+00:00")
            now = datetime.fromisoformat(client_time_str)
        except Exception as e:
            logger.warning(f"Failed to parse user client created_at: {user.created_at}. Error: {e}")
    
    try:
        validate_age_limit(user.dob, now)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 4. Validate username with Ollama
    is_human = await validate_human_name(user.username)
    if not is_human:
        raise HTTPException(status_code=400, detail="Username must be a human name (non-living things, animals, etc. are not allowed).")
        
    # Check uniqueness
    existing_user = await db.database.users.find_one({
        "$or": [
            {"username": user.username},
            {"email": user.email}
        ]
    })
    if existing_user:
        if existing_user.get("username") == user.username:
            raise HTTPException(status_code=409, detail="Username is already taken.")
        else:
            raise HTTPException(status_code=409, detail="Email is already registered.")
            
    # Auto-generate next user ID
    user_ids = []
    async for doc in db.database.users.find({}, {"id": 1}):
        val = doc.get("id", "")
        if val.startswith("USr-"):
            try:
                user_ids.append(int(val.split("-")[1]))
            except Exception:
                pass
    next_num = max(user_ids) + 1 if user_ids else 1001
    user_id = f"USr-{next_num}"
    
    plan_color = "bg-[#E9C176] text-[#261900]" if user.plan == "Pro" else "bg-[#E7E8EA] text-[#44474D]"
    
    new_user = {
        "id": user_id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "org": user.org,
        "plan": user.plan,
        "planColor": plan_color,
        "status": "Active",
        "statusColor": "bg-[#22C55E]",
        "dob": user.dob,
        "gender": user.gender,
        "password": user.password,
        "phone_no": user.phone_no,
        "created_at": now
    }
    
    await db.database.users.insert_one(new_user)
    new_user["_id"] = str(new_user["_id"])
    new_user["created_at"] = new_user["created_at"].isoformat()
    return new_user


@router.get("/users/check-username")
async def check_username_availability(username: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    user = await db.database.users.find_one({"username": username})
    return {"available": user is None}


@router.get("/users/check-email")
async def check_email_availability(email: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    user = await db.database.users.find_one({"email": email})
    return {"available": user is None}


class UserLoginRequest(BaseModel):
    email: str
    password: str


@router.post("/users/login")
async def user_login(body: UserLoginRequest):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    user = await db.database.users.find_one({"email": body.email})
    if not user or user.get("password") != body.password:
        raise HTTPException(status_code=401, detail="Invalid Email or Password.")
        
    if user.get("status") != "Active" or user.get("isActive") is False:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Your account has been deactivated. Do you want to reactivate your account?",
                "is_deactivated": True,
                "email": user.get("email"),
            },
        )
        
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "name": user.get("name"),
        "email": user.get("email"),
        "plan": user.get("plan"),
        "message": "Login successful"
    }


@router.put("/users/{user_id}")
async def update_user(user_id: str, user: UserUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing_user = await db.database.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    # 1. Validate Email
    try:
        validate_email_domain(user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 2. Validate Password
    try:
        validate_password_strength(user.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 3. Validate DOB based on original registration date
    reg_date = existing_user.get("created_at") or datetime.now(timezone.utc)
    try:
        validate_age_limit(user.dob, reg_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 4. Validate username with Ollama
    if user.username != existing_user.get("username"):
        is_human = await validate_human_name(user.username)
        if not is_human:
            raise HTTPException(status_code=400, detail="Username must be a human name (non-living things, animals, etc. are not allowed).")
            
        dup = await db.database.users.find_one({"username": user.username})
        if dup and dup.get("id") != user_id:
            raise HTTPException(status_code=409, detail="Username is already taken.")
            
    if user.email != existing_user.get("email"):
        dup = await db.database.users.find_one({"email": user.email})
        if dup and dup.get("id") != user_id:
            raise HTTPException(status_code=409, detail="Email is already registered.")
            
    plan_color = "bg-[#E9C176] text-[#261900]" if user.plan == "Pro" else "bg-[#E7E8EA] text-[#44474D]"
    
    update_doc = {
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "org": user.org,
        "plan": user.plan,
        "planColor": plan_color,
        "dob": user.dob,
        "gender": user.gender,
        "password": user.password,
        "phone_no": user.phone_no
    }
    
    await db.database.users.update_one({"id": user_id}, {"$set": update_doc})
    
    updated = await db.database.users.find_one({"id": user_id})
    updated["_id"] = str(updated["_id"])
    if "created_at" in updated and updated["created_at"]:
        if isinstance(updated["created_at"], datetime):
            updated["created_at"] = updated["created_at"].isoformat()
    return updated


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing_user = await db.database.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    await db.database.users.delete_one({"id": user_id})
    return {"message": "User deleted successfully.", "id": user_id}

class UserPlanUpdate(BaseModel):
    plan: str

@router.put("/users/{user_id}/plan")
async def update_user_plan(user_id: str, body: UserPlanUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    allowed_plans = {"Standard", "Pro"}
    if body.plan not in allowed_plans:
        raise HTTPException(status_code=400, detail=f"Plan must be one of: {', '.join(allowed_plans)}")

    existing_user = await db.database.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found.")

    await db.database.users.update_one(
        {"id": user_id},
        {"$set": {"plan": body.plan}}
    )
    return {"message": "Plan updated successfully.", "id": user_id, "plan": body.plan}


# ----------------------------
# Support Query Management
# ----------------------------

class SupportQueryCreate(BaseModel):
    full_name: str
    email: str
    subject: str
    message: str


class SupportStatusUpdate(BaseModel):
    status: str  # "Urgent", "Pending", "Solved"


@router.post("/support")
async def create_support_query(query: SupportQueryCreate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    # Validate email domain
    if not query.email.strip().lower().endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Email must be a @gmail.com domain.")

    if not query.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not query.subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required.")
    if not query.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")

    now = datetime.now(timezone.utc)

    # Auto-generate query_id
    query_ids = []
    async for doc in db.database.support_queries.find({}, {"query_id": 1}):
        val = doc.get("query_id", "")
        if val.startswith("CQ") or val.startswith("SQ-"):
            try:
                # Handle old 'SQ-XXXX' and new 'CQXXXX'
                if val.startswith("CQ"):
                    query_ids.append(int(val[2:]))
                else:
                    query_ids.append(int(val.split("-")[1]))
            except Exception:
                pass
    next_num = max(query_ids) + 1 if query_ids else 1
    query_id = f"CQ{next_num:04d}"

    new_query = {
        "query_id": query_id,
        "full_name": query.full_name.strip(),
        "email": query.email.strip(),
        "subject": query.subject.strip(),
        "message": query.message.strip(),
        "status": "Pending",
        "created_at": now,
    }

    await db.database.support_queries.insert_one(new_query)
    new_query["_id"] = str(new_query["_id"])
    new_query["created_at"] = new_query["created_at"].isoformat()

    # Dispatch email to admin (verdictaisupport@gmail.com) and user acknowledgement
    try:
        await send_contact_notification(
            name=query.full_name.strip(),
            email=query.email.strip(),
            subject=query.subject.strip(),
            message=query.message.strip(),
            query_id=query_id
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch contact notification to admin: {e}")

    try:
        await send_contact_acknowledgement(
            name=query.full_name.strip(),
            email=query.email.strip(),
            subject=query.subject.strip(),
            query_id=query_id
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch contact acknowledgement to client: {e}")

    return new_query


@router.get("/support")
async def get_support_queries():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    cursor = db.database.support_queries.find({}).sort("created_at", -1)
    queries = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if "created_at" in doc and doc["created_at"]:
            if isinstance(doc["created_at"], datetime):
                # Ensure the retrieved naive UTC datetime is made timezone-aware
                # before converting to isoformat so JS parses it as UTC
                aware_dt = doc["created_at"].replace(tzinfo=timezone.utc) if doc["created_at"].tzinfo is None else doc["created_at"]
                doc["created_at"] = aware_dt.isoformat()
        queries.append(doc)

    total = len(queries)
    resolved = sum(1 for q in queries if q.get("status") == "Solved")
    pending = sum(1 for q in queries if q.get("status") == "Pending")
    urgent = sum(1 for q in queries if q.get("status") == "Urgent")

    return {
        "queries": queries,
        "total": total,
        "resolved": resolved,
        "pending": pending,
        "urgent": urgent,
    }


@router.put("/support/{query_id}/status")
async def update_support_status(query_id: str, body: SupportStatusUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    allowed = {"Urgent", "Pending", "Solved"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(allowed)}")

    existing = await db.database.support_queries.find_one({"query_id": query_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Support query not found.")

    await db.database.support_queries.update_one(
        {"query_id": query_id},
        {"$set": {"status": body.status}},
    )

    return {"message": "Status updated.", "query_id": query_id, "status": body.status}

@router.delete("/support/{query_id}")
async def delete_support_query(query_id: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    existing = await db.database.support_queries.find_one({"query_id": query_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Support query not found.")

    await db.database.support_queries.delete_one({"query_id": query_id})
    return {"message": "Support query deleted successfully.", "query_id": query_id}


class AdminLoginRequest(BaseModel):
    adminid: str
    password: str


@router.post("/login")
async def admin_login(body: AdminLoginRequest):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    admin = await db.database.admins.find_one({"adminid": body.adminid})
    if not admin or admin.get("password") != body.password:
        raise HTTPException(status_code=401, detail="Invalid Admin ID or Password.")

    return {
        "adminid": admin.get("adminid"),
        "name": admin.get("name", "Admin"),
        "role": admin.get("role", "admin"),
        "message": "Login successful",
    }


class AdminProfileUpdate(BaseModel):
    original_adminid: str
    adminid: str
    password: str
    dob: str
    name: str


@router.put("/profile")
async def update_admin_profile(body: AdminProfileUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    # 1. Validate original admin exists
    admin = await db.database.admins.find_one({"adminid": body.original_adminid})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin account not found.")

    # 2. Check for unique adminid if changed
    if body.adminid != body.original_adminid:
        dup = await db.database.admins.find_one({"adminid": body.adminid})
        if dup:
            raise HTTPException(status_code=409, detail="Admin ID is already taken by another account.")

    # 3. Validate fields are not empty
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    if not body.adminid.strip():
        raise HTTPException(status_code=400, detail="Admin ID cannot be empty.")
    
    # Validate password strength
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    try:
        # Validate DOB format (YYYY-MM-DD)
        datetime.strptime(body.dob, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date of Birth must be in YYYY-MM-DD format.")

    # 4. Perform update
    await db.database.admins.update_one(
        {"adminid": body.original_adminid},
        {"$set": {
            "adminid": body.adminid.strip(),
            "password": body.password,
            "dob": body.dob,
            "name": body.name.strip()
        }}
    )

    # 5. Return updated admin info
    return {
        "adminid": body.adminid.strip(),
        "name": body.name.strip(),
        "dob": body.dob,
        "role": admin.get("role", "admin"),
        "message": "Profile updated successfully."
    }


@router.get("/profile")
async def get_admin_profile(adminid: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    admin = await db.database.admins.find_one({"adminid": adminid}, {"_id": 0})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin account not found.")
        
    return admin


class AdminCreate(BaseModel):
    adminid: str
    name: str
    email: str
    role: str
    dob: str
    password: str

class AdminUpdate(BaseModel):
    adminid: str
    name: str
    email: str
    role: str
    dob: str
    password: str

@router.get("/admins")
async def get_admins():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    # Check if the email field exists in any admin documents, if not set it to adminid
    await db.database.admins.update_many(
        {"email": {"$exists": False}},
        [{"$set": {"email": "$adminid"}}]
    )
    
    cursor = db.database.admins.find({}, {"_id": 0})
    admins = await cursor.to_list(length=None)
    
    total = len(admins)
    super_admins = sum(1 for a in admins if a.get("role") == "super_admin")
    standard_admins = sum(1 for a in admins if a.get("role") == "admin")
    
    return {
        "admins": admins,
        "total": total,
        "super_admins": super_admins,
        "standard_admins": standard_admins
    }

@router.post("/admins")
async def create_admin(body: AdminCreate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    
    adminid = body.adminid.strip()
    name = body.name.strip()
    email = body.email.strip()
    role = body.role.strip()
    dob = body.dob.strip()
    password = body.password
    
    if not adminid or not name or not email or not role or not dob or not password:
        raise HTTPException(status_code=400, detail="All fields are required.")
        
    # Check uniqueness of adminid
    existing_id = await db.database.admins.find_one({"adminid": adminid})
    if existing_id:
        raise HTTPException(status_code=409, detail="Admin ID is already registered.")
        
    # Check uniqueness of email
    existing_email = await db.database.admins.find_one({"email": email})
    if existing_email:
        raise HTTPException(status_code=409, detail="Email is already registered.")
        
    # Validate password strength
    try:
        validate_password_strength(password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    try:
        # Validate date format (YYYY-MM-DD)
        datetime.strptime(dob, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date of Birth must be in YYYY-MM-DD format.")
        
    new_admin = {
        "adminid": adminid,
        "name": name,
        "email": email,
        "role": role,
        "dob": dob,
        "password": password,
        "gender": "Male"
    }
    
    await db.database.admins.insert_one(new_admin)
    return {"message": "Admin created successfully."}

@router.put("/admins/{adminid_param}")
async def update_admin(adminid_param: str, body: AdminUpdate):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing = await db.database.admins.find_one({"adminid": adminid_param})
    if not existing:
        raise HTTPException(status_code=404, detail="Admin account not found.")
        
    adminid = body.adminid.strip()
    name = body.name.strip()
    email = body.email.strip()
    role = body.role.strip()
    dob = body.dob.strip()
    password = body.password
    
    if not adminid or not name or not email or not role or not dob or not password:
        raise HTTPException(status_code=400, detail="All fields are required.")
        
    # If adminid is changed, check uniqueness
    if adminid != adminid_param:
        dup = await db.database.admins.find_one({"adminid": adminid})
        if dup:
            raise HTTPException(status_code=409, detail="Admin ID is already registered.")
            
    # If email is changed, check uniqueness
    if email != existing.get("email"):
        dup = await db.database.admins.find_one({"email": email})
        if dup:
            raise HTTPException(status_code=409, detail="Email is already registered.")
            
    # Validate password strength
    try:
        validate_password_strength(password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    try:
        datetime.strptime(dob, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date of Birth must be in YYYY-MM-DD format.")
        
    await db.database.admins.update_one(
        {"adminid": adminid_param},
        {"$set": {
            "adminid": adminid,
            "name": name,
            "email": email,
            "role": role,
            "dob": dob,
            "password": password
        }}
    )
    return {"message": "Admin updated successfully."}

@router.delete("/admins/{adminid_param}")
async def delete_admin(adminid_param: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
        
    existing = await db.database.admins.find_one({"adminid": adminid_param})
    if not existing:
        raise HTTPException(status_code=404, detail="Admin account not found.")
        
    await db.database.admins.delete_one({"adminid": adminid_param})
    return {"message": "Admin deleted successfully."}



