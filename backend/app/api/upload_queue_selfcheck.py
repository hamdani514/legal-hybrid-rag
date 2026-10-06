"""
Self-check for several admin uploads at once (the upload queue in admin.py).

    cd backend && DB_NAME=legal_rag_scratch_upload venv/Scripts/python.exe -m app.api.upload_queue_selfcheck

* Runs the real FastAPI app in-process (httpx ASGITransport) against a scratch
  MongoDB database, which it drops at the end. It refuses to run otherwise.
* The heavy stages (extraction/OCR, the Gemini parse, the tree, the search
  stores, Google Drive) are replaced by stand-ins that record which judgment
  they were called for and how many run at once. What is tested is the queue
  and the isolation around them, not the stages themselves (each has its own
  checks): no store, model or Gemini quota is touched.
* Uploaded stand-in PDFs are written to backend/uploads/ under fresh uuid
  names and removed at the end.
"""

import asyncio  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

SCRATCH = "legal_rag_scratch_upload"
assert settings.DB_NAME == SCRATCH, f"refusing to run against {settings.DB_NAME!r}"

import main  # noqa: E402
import app.api.admin as admin_mod  # noqa: E402
import app.indexing.sync as sync_mod  # noqa: E402
import app.ingestion.tree_builder as tree_mod  # noqa: E402
import app.ingestion.validator as validator_mod  # noqa: E402
from app.database import connect_db, db  # noqa: E402

RESULTS: list = []
N_FILES = 8
SLOTS = 2


def check(name: str, cond: bool, info: str = "") -> None:
    RESULTS.append((name, bool(cond), info))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({info})" if info else ""))


class Meter:
    """Concurrent-use counter that also works across worker threads."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.now = 0
        self.peak = 0

    def enter(self) -> None:
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)

    def leave(self) -> None:
        with self.lock:
            self.now -= 1


pipeline_meter, index_meter = Meter(), Meter()
seen: dict[str, list] = {}  # pdf_id -> [(stage, value it was given)]


def _saw(pdf_id: str, stage: str, value: str) -> None:
    seen.setdefault(pdf_id, []).append((stage, value))


def fake_extract(pdf_path: str, pdf_id: str, detected_type: str) -> str:
    time.sleep(0.15)  # runs in a worker thread, like OCR
    with open(pdf_path, "rb") as f:
        marker = f.read().decode("latin-1").split("MARKER:")[1].strip()
    _saw(pdf_id, "extract", marker)
    return f"TEXT-OF {marker}"


async def fake_parse(pdf_id: str, extracted_text: str) -> dict:
    await asyncio.sleep(0.1)
    _saw(pdf_id, "parse", extracted_text.replace("TEXT-OF ", ""))
    return {"pdf_id": pdf_id, "parse_mode": "stub", "confidence_score": 1.0, "quality_passed": True,
            "quality_issues": [], "sections": [{"section_type": "FACTS", "text": extracted_text}]}


async def fake_tree(pdf_id: str, final) -> None:
    if final:
        _saw(pdf_id, "tree", final["sections"][0]["text"].replace("TEXT-OF ", ""))
    await db.database.document_trees.update_one({"pdf_id": pdf_id}, {"$set": {"pdf_id": pdf_id}}, upsert=True)


async def fake_complete(judgment_id: str, build_card: bool = False, force_dense: bool = False) -> dict:
    index_meter.enter()
    try:
        tree = await db.database.document_trees.find_one({"pdf_id": judgment_id})
        _saw(judgment_id, "index", "tree-present" if tree else "tree-missing")
        await asyncio.sleep(0.2)
        await db.documents.update_one({"pdf_id": judgment_id}, {"$set": {"status": "searchable"}})
        return {"stores": {}, "report": {}}
    finally:
        index_meter.leave()


async def fake_warm() -> None:
    return None


class FakeDrive:
    target_email = "selfcheck@example.com"

    async def upload_file(self, file_path, original_filename, mime_type):
        return {"file_id": f"drive-{uuid.uuid4()}", "file_name": original_filename, "status": "uploaded"}


def pdf_bytes(marker: str) -> bytes:
    return f"%PDF-1.4\n% stand-in judgment\nMARKER: {marker}\n".encode()


async def run() -> None:
    settings.ADMIN_INGEST_CONCURRENCY = SLOTS
    admin_mod.extract = fake_extract
    admin_mod.parse_sections = fake_parse
    admin_mod.detect_pdf_type = lambda path: "text"
    tree_mod.ensure_tree = fake_tree
    sync_mod.complete_judgment = fake_complete
    sync_mod.warm_imports = fake_warm
    validator_mod.validate_judgment = lambda path: (True, "ok")
    import app.services.google_drive_service as drive_mod
    drive_mod.google_drive_service = FakeDrive()

    original_pipeline = admin_mod._run_pipeline

    async def metered_pipeline(pdf_id, pdf_path, detected_type):
        pipeline_meter.enter()
        try:
            await original_pipeline(pdf_id, pdf_path, detected_type)
        finally:
            pipeline_meter.leave()

    admin_mod._run_pipeline = metered_pipeline

    await connect_db()
    assert db.database.name == SCRATCH, db.database.name
    await db.client.drop_database(SCRATCH)

    markers = [f"case-{i}-{uuid.uuid4().hex[:6]}" for i in range(N_FILES)]
    created: list[str] = []
    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
            async def upload(name: str, content: bytes):
                return await c.post("/api/admin/upload", files={"file": (name, content, "application/pdf")})

            # All files at once, plus a second copy of the first one in the same batch.
            batch = [upload(f"{m}.pdf", pdf_bytes(m)) for m in markers]
            batch.append(upload("copy-of-first.pdf", pdf_bytes(markers[0])))
            responses = await asyncio.gather(*batch)

            ok = [r for r in responses if r.status_code == 200]
            dup = [r for r in responses if r.status_code == 409]
            check(f"{N_FILES} distinct PDFs accepted", len(ok) == N_FILES, f"{len(ok)} accepted")
            check("same PDF twice in one batch: exactly one rejected as duplicate",
                  len(dup) == 1 and "Duplicate" in dup[0].json().get("detail", ""),
                  dup[0].json().get("detail", "") if dup else "no 409")
            ids = {r.json()["pdf_id"]: r.json()["filename"] for r in ok}
            created = list(ids)
            check("every upload got its own pdf_id", len(ids) == N_FILES)

            # While the batch drains, waiting jobs must report active (not stalled).
            await asyncio.sleep(0.05)
            r = await c.post("/api/admin/jobs/lookup", json={"job_ids": created})
            jobs = r.json()["jobs"]
            waiting = [j for j in jobs if j["status"] == "queued"]
            check("lookup returns only the batch's jobs", r.status_code == 200 and len(jobs) == N_FILES,
                  f"{len(jobs)} jobs")
            check("queued jobs exist and are marked active", waiting and all(j["active"] for j in waiting),
                  f"{len(waiting)} queued")

            deadline = time.time() + 60
            while time.time() < deadline:
                r = await c.post("/api/admin/jobs/lookup", json={"job_ids": created})
                if all(j["status"] == "searchable" for j in r.json()["jobs"]):
                    break
                await asyncio.sleep(0.2)
            final = {j["job_id"]: j for j in r.json()["jobs"]}
            check("every judgment finished searchable",
                  all(final[i]["status"] == "searchable" for i in created),
                  str(sorted({j['status'] for j in final.values()})))
            check("finished jobs are no longer active", not any(j["active"] for j in final.values()))

            check(f"at most {SLOTS} judgments in the pipeline at once", 1 <= pipeline_meter.peak <= SLOTS,
                  f"peak {pipeline_meter.peak}")
            check("the pipeline actually ran in parallel", pipeline_meter.peak == SLOTS,
                  f"peak {pipeline_meter.peak}")
            check("index stage never ran two judgments at once", index_meter.peak == 1,
                  f"peak {index_meter.peak}")

            # Isolation: every stage of a judgment saw that judgment's own file.
            mixed = []
            for pdf_id, filename in ids.items():
                own = filename[:-4]
                stages = seen.get(pdf_id, [])
                values = {stage: value for stage, value in stages}
                if values.get("extract") != own or values.get("parse") != own or values.get("tree") != own \
                        or values.get("index") != "tree-present":
                    mixed.append((filename, values))
            check("no judgment saw another judgment's data", not mixed, str(mixed[:2]))
            docs = await db.documents.count_documents({})
            check("one document record per distinct PDF", docs == N_FILES, f"{docs} documents")

            # Deleting a queued job cancels it and removes its files.
            m = f"late-{uuid.uuid4().hex[:6]}"
            first = [await upload(f"{m}-{k}.pdf", pdf_bytes(f"{m}-{k}")) for k in range(SLOTS + 1)]
            late_id = first[-1].json()["pdf_id"]
            created += [x.json()["pdf_id"] for x in first]
            r = await c.delete(f"/api/admin/jobs/{late_id}")
            await asyncio.sleep(0.3)
            left = [p.name for p in admin_mod.UPLOADS_DIR.glob(f"{late_id}*")]
            check("deleting a waiting upload cancels it and leaves no files",
                  r.status_code == 200 and not left and late_id not in admin_mod.ACTIVE_INGESTION_TASKS,
                  f"{r.status_code}, files left: {left}")
            for _ in range(100):  # let the rest of that mini-batch finish before cleanup
                if not any(admin_mod._ingestion_running(x) for x in created):
                    break
                await asyncio.sleep(0.1)
    finally:
        for pdf_id in created:
            admin_mod._remove_upload_files(pdf_id)
        await db.client.drop_database(SCRATCH)
        names = await db.client.list_database_names()
        check("scratch DB dropped", SCRATCH not in names)


if __name__ == "__main__":
    asyncio.run(run())
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    raise SystemExit(0 if passed == len(RESULTS) else 1)
