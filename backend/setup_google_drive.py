#!/usr/bin/env python3
"""
Google Drive Setup & Verification Utility for Verdict AI.
Target Account: verdictaisupport@gmail.com

Usage:
  # Check current status
  python setup_google_drive.py status

  # Authenticate with OAuth 2.0 (creates token.json for verdictaisupport@gmail.com)
  python setup_google_drive.py auth --client-secrets client_secret.json

  # Test upload and download
  python setup_google_drive.py test
"""

import argparse
import io
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings
from app.services.google_drive_service import google_drive_service, SCOPES


def check_status():
    print("=" * 60)
    print("Verdict AI — Google Drive Integration Status")
    print(f"Target Account: {settings.GOOGLE_DRIVE_TARGET_EMAIL}")
    print("=" * 60)

    status = google_drive_service.get_auth_status()
    print(f"Configured:             {status['configured']}")
    print(f"Auth Method:            {status['auth_method'] or 'None (Fallback mode)'}")
    print(f"Folder ID:              {status['folder_id']}")
    print(f"Service Account File:   {status['service_account_file']}")
    print(f"OAuth Token File:       {status['token_file']}")

    if not status["configured"]:
        print("\n[!] Setup Instructions:")
        print("To connect Google Drive for verdictaisupport@gmail.com, choose ONE of these methods:")
        print("\nMETHOD 1 (Recommended for Servers - Service Account):")
        print("1. Go to https://console.cloud.google.com and enable 'Google Drive API'.")
        print("2. Create a Service Account, generate a JSON key, and save it as 'backend/service_account.json'.")
        print(f"3. In verdictaisupport@gmail.com's Google Drive, create a folder 'Verdict AI Judgments'.")
        print("4. Share that folder with your Service Account email (give 'Editor' permission).")
        print("5. Put GOOGLE_DRIVE_FOLDER_ID=<folder_id> in backend/.env")
        print("\nMETHOD 2 (Interactive OAuth 2.0):")
        print("1. In Google Cloud Console, create an OAuth 2.0 Client ID (Desktop App).")
        print("2. Download the JSON credentials as 'backend/client_secret.json'.")
        print("3. Run: python setup_google_drive.py auth")
        print("4. Log in with verdictaisupport@gmail.com in your browser when prompted.")
    else:
        print("\n[OK] Google Drive is properly configured and ready for uploads!")


def run_oauth_flow(client_secrets_path: str):
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets_file = Path(client_secrets_path)
    if not secrets_file.exists():
        secrets_file = Path(__file__).resolve().parent / client_secrets_path

    if not secrets_file.exists():
        print(f"Error: Client secrets file not found at: {client_secrets_path}")
        print("Please download your OAuth client secret JSON from Google Cloud Console first.")
        sys.exit(1)

    print(f"Starting OAuth authorization flow using: {secrets_file}")
    print(f"Please log in with: {settings.GOOGLE_DRIVE_TARGET_EMAIL}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
    creds = flow.run_local_server(port=0)

    token_file = Path(__file__).resolve().parent / settings.GOOGLE_DRIVE_TOKEN_FILE
    with open(token_file, "w", encoding="utf-8") as token:
        token.write(creds.to_json())

    print(f"\n[OK] Successfully authenticated! Token saved to: {token_file}")
    print(f"Verdict AI can now upload judgment PDFs to {settings.GOOGLE_DRIVE_TARGET_EMAIL}'s Google Drive.")

    # Reset cached service so it picks up the new token
    google_drive_service._service = None

    print("\nSynchronizing pending judgments to Google Drive...")
    import asyncio
    asyncio.run(sync_pending_documents())


async def test_integration():
    import asyncio
    print("\nRunning Google Drive upload and download verification test...")
    service = google_drive_service.get_service()
    if not service:
        print("[!] Warning: Google Drive client is not configured yet. Testing fallback behavior...")

    test_file = Path(__file__).resolve().parent / "uploads" / "test_judgment.pdf"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_bytes(b"%PDF-1.4\n% Verdict AI Test PDF Judgment\n%%EOF")

    try:
        # Test Upload
        print("Uploading test document...")
        upload_res = await google_drive_service.upload_file(
            file_path=test_file,
            original_filename="Test_Judgment_2026.pdf",
            mime_type="application/pdf",
        )
        print("Upload Result:", upload_res)
        file_id = upload_res.get("file_id")

        # Test Download
        print(f"Downloading stream for file_id: {file_id}...")
        stream, name, mime = await google_drive_service.download_file_stream(file_id, fallback_filename="Test.pdf")
        content = stream.read()
        print(f"Successfully downloaded {len(content)} bytes. Name: {name}, Mime: {mime}")

        print("\n[OK] Verification test completed successfully!")
    finally:
        if test_file.exists():
            test_file.unlink()


async def sync_pending_documents():
    from datetime import datetime, timezone
    from app.database import connect_db, db

    print("\nConnecting to database to check for pending judgments...")
    await connect_db()

    if not google_drive_service.is_configured():
        print("[!] Error: Google Drive is not configured yet.")
        print("Please authenticate using 'python setup_google_drive.py auth' or provide service_account.json first.")
        return

    cursor = db.documents.find({
        "$or": [
            {"drive.status": "local_fallback"},
            {"drive.file_id": {"$regex": "^local_"}},
            {"drive": {"$exists": False}}
        ]
    })
    docs = await cursor.to_list(length=None)

    if not docs:
        print("[OK] All documents in MongoDB are already synchronized with Google Drive!")
        return

    print(f"Found {len(docs)} document(s) with pending Google Drive upload:")
    uploads_dir = Path(__file__).resolve().parent / "uploads"
    success_count = 0

    for doc in docs:
        pdf_id = doc.get("pdf_id")
        filename = doc.get("filename", f"{pdf_id}.pdf")
        local_path = uploads_dir / f"{pdf_id}.pdf"

        if not local_path.exists():
            print(f"  [-] File not found locally: {local_path} (Skipping)")
            continue

        print(f"  [>] Uploading '{filename}' (ID: {pdf_id}) to Google Drive...")
        res = await google_drive_service.upload_file(
            file_path=local_path,
            original_filename=filename,
            mime_type="application/pdf",
        )

        drive_file_id = res.get("file_id")
        drive_status = res.get("status")

        if drive_status == "uploaded":
            now = datetime.now(timezone.utc)
            await db.documents.update_one(
                {"pdf_id": pdf_id},
                {
                    "$set": {
                        "drive": {
                            "file_id": drive_file_id,
                            "file_name": res.get("file_name", filename),
                            "mime_type": res.get("mime_type", "application/pdf"),
                            "web_view_link": res.get("web_view_link"),
                            "web_content_link": res.get("web_content_link"),
                            "uploaded_at": now,
                            "account": google_drive_service.target_email,
                            "status": "uploaded",
                        }
                    }
                },
            )
            await db.jobs.update_one(
                {"job_id": pdf_id},
                {
                    "$set": {
                        "drive_file_id": drive_file_id,
                        "drive_status": "uploaded",
                    }
                },
            )
            print(f"      [OK] Uploaded! Drive File ID: {drive_file_id}")
            success_count += 1
        else:
            print(f"      [-] Failed to upload: {res.get('error')}")

    print(f"\n[OK] Successfully synchronized {success_count} / {len(docs)} documents to {settings.GOOGLE_DRIVE_TARGET_EMAIL}'s Google Drive.")


def main():
    parser = argparse.ArgumentParser(description="Google Drive utility for Verdict AI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("status", help="Show Google Drive configuration status")

    auth_parser = subparsers.add_parser("auth", help="Authenticate with Google OAuth 2.0")
    auth_parser.add_argument(
        "--client-secrets",
        default="client_secret.json",
        help="Path to client_secret.json from Google Cloud Console",
    )

    subparsers.add_parser("test", help="Test upload and download")
    subparsers.add_parser("sync", help="Sync pending local judgments to Google Drive")

    args = parser.parse_args()

    if args.command == "auth":
        run_oauth_flow(args.client_secrets)
    elif args.command == "test":
        import asyncio
        asyncio.run(test_integration())
    elif args.command == "sync":
        import asyncio
        asyncio.run(sync_pending_documents())
    else:
        check_status()


if __name__ == "__main__":
    main()
