"""
Back up the MongoDB database to one file, and restore it.

    cd backend
    venv/Scripts/python.exe -m scripts.backup_db                       # back up DB_NAME
    venv/Scripts/python.exe -m scripts.backup_db --with-indexes        # also the search stores
    venv/Scripts/python.exe -m scripts.backup_db --keep 14             # then keep the newest 14
    venv/Scripts/python.exe -m scripts.backup_db --copy-to D:/backups  # and a copy elsewhere
    venv/Scripts/python.exe -m scripts.backup_db --restore FILE --into legal_rag_restored

A backup is a zip in backend/backups (BACKUP_DIR to change it) holding one
JSON-lines file per collection, in MongoDB's extended JSON so ObjectIds and
dates come back as they were, the collections' indexes, a manifest with the
document counts, and backend/uploads (the uploaded judgment PDFs and their
extracted text, avatars and covers stored locally). Users, chats, payments,
case cards and judgment sections are all collections, so all are included.

--copy-to DIR (or BACKUP_COPY_DIR) also copies each backup to a second place
and keeps the same number there: another disk, a network share, or a folder a
cloud-sync client uploads. A backup on the same disk as the database does not
survive that disk.

The server also runs this itself (scheduled_tasks.py): daily at
BACKUP_HOUR_UTC, keeping BACKUP_KEEP; and weekly with the search indexes
("-full" backups, keeping BACKUP_FULL_KEEP), since rebuilding those takes hours.

--with-indexes adds the search stores (backend/chroma_db and lexical.db,
about 1 GB). They can be rebuilt from the database, but that takes hours of
embedding, so keep a copy of them from time to time.

Restoring writes only into the database named by --into. A database that
already holds data is refused unless --drop is given, and the live database
(DB_NAME) also needs --i-mean-the-live-db. Restore into a new name, check it,
then point DB_NAME at it.

Run it on a schedule (cron, or Windows Task Scheduler) and copy the zips off
the server: a backup on the same disk does not survive the disk.

A backup holds every user's personal data, so it is ENCRYPTED when
BACKUP_ENCRYPTION_KEY is set (AES-256-GCM, written as name.zip.enc): a copy that
leaves the server (BACKUP_COPY_DIR, a cloud folder) is unreadable without the
key. Make a key once with

    venv/Scripts/python.exe -m scripts.backup_db --make-key

put it in the server's .env AND somewhere safe off the server (a password
manager): without it no backup can be restored. Without a key, backups are
still made, unencrypted, and every run logs an ERROR saying so.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

from loguru import logger

from app.config import settings

BACKEND = Path(__file__).resolve().parents[1]
FORMAT = 1


# ── Encryption: AES-256-GCM in 4 MB chunks (a 1 GB backup never sits in memory) ──
# File: MAGIC, an 8-byte random nonce prefix, then per chunk a 4-byte length and
# the ciphertext. Each chunk's nonce is prefix + its 4-byte number, and its
# associated data says whether it is the last one, so a reordered, altered or
# cut-off file fails to decrypt instead of restoring half a database.
MAGIC = b"LRAGBK1\n"
CHUNK = 4 * 1024 * 1024


def make_key() -> str:
    import base64
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def _key() -> bytes | None:
    import base64
    raw = (os.getenv("BACKUP_ENCRYPTION_KEY") or getattr(settings, "BACKUP_ENCRYPTION_KEY", "") or "").strip()
    if not raw:
        return None
    key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(key) != 32:
        raise ValueError("BACKUP_ENCRYPTION_KEY must be 32 bytes, base64 (make one with --make-key)")
    return key


def _aad(index: int, last: bool) -> bytes:
    return MAGIC + index.to_bytes(4, "big") + (b"\x01" if last else b"\x00")


def encrypt_file(src: Path, dst: Path, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aes, prefix = AESGCM(key), os.urandom(8)
    size = src.stat().st_size
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(MAGIC + prefix)
        index, done = 0, 0
        while True:
            chunk = fin.read(CHUNK)
            done += len(chunk)
            last = done >= size
            sealed = aes.encrypt(prefix + index.to_bytes(4, "big"), chunk, _aad(index, last))
            fout.write(len(sealed).to_bytes(4, "big") + sealed)
            index += 1
            if last:
                break


def decrypt_file(src: Path, dst: Path, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aes = AESGCM(key)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        if fin.read(len(MAGIC)) != MAGIC:
            raise ValueError("not an encrypted backup")
        prefix, index = fin.read(8), 0
        while True:
            head = fin.read(4)
            if len(head) < 4:
                raise ValueError("the backup is cut off (no final chunk)")
            sealed = fin.read(int.from_bytes(head, "big"))
            nonce = prefix + index.to_bytes(4, "big")
            try:
                fout.write(aes.decrypt(nonce, sealed, _aad(index, False)))
            except Exception:  # noqa: BLE001 - maybe the last chunk
                fout.write(aes.decrypt(nonce, sealed, _aad(index, True)))  # raises if tampered or wrong key
                if fin.read(1):
                    raise ValueError("data after the final chunk") from None
                return
            index += 1


def _kind_full(path: Path) -> bool:
    return path.name.split(".zip")[0].endswith("-full")


def backup_dir() -> Path:
    return Path(os.getenv("BACKUP_DIR") or getattr(settings, "BACKUP_DIR", "") or BACKEND / "backups")


def uploads_dir() -> Path:
    return BACKEND / "uploads"


def _sqlite_copy(src_path: Path, zf: zipfile.ZipFile, arc: str) -> None:
    """A consistent copy of a SQLite file even while the server writes to it."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / src_path.name
        src, dst = sqlite3.connect(src_path), sqlite3.connect(copy)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        zf.write(copy, arc)


def _client() -> MongoClient:
    return MongoClient(settings.MONGO_URL, serverSelectionTimeoutMS=10000)


def backup(db_name: str, with_indexes: bool = False, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or backup_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = out_dir / f"{db_name}-{stamp}{'-full' if with_indexes else ''}.zip"
    partial = final.with_suffix(".zip.partial")  # never leave a half-written backup looking complete
    db = _client()[db_name]
    manifest = {"format": FORMAT, "database": db_name, "created_at": stamp, "collections": {}, "files": [],
                "uploads": []}
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for name in sorted(db.list_collection_names()):
            if name.startswith("system."):
                continue
            count = 0
            with zf.open(f"collections/{name}.jsonl", "w", force_zip64=True) as fh:
                for doc in db[name].find({}, no_cursor_timeout=False).batch_size(1000):
                    fh.write(json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS).encode("utf-8") + b"\n")
                    count += 1
            indexes = [
                {"keys": list(spec["key"].items()), **{k: v for k, v in spec.items() if k not in ("key", "v", "ns")}}
                for spec in db[name].list_indexes() if spec["name"] != "_id_"
            ]
            manifest["collections"][name] = {"count": count, "indexes": indexes}
            print(f"  {name:<28} {count:>8} documents")
        uploads = uploads_dir()
        if uploads.is_dir():
            for path in sorted(uploads.rglob("*")):
                if path.is_file():
                    arc = "uploads/" + path.relative_to(uploads).as_posix()
                    zf.write(path, arc)
                    manifest["uploads"].append(arc)
        print(f"  uploads: {len(manifest['uploads'])} files")
        if with_indexes:
            manifest["files"] = _add_search_stores(zf)
        zf.writestr("manifest.json", json_util.dumps(manifest, indent=2))
    key = _key()
    if key is None:
        partial.replace(final)
        logger.error(f"Backup {final.name} is NOT encrypted: it holds every user's personal data in plain form. "
                     "Set BACKUP_ENCRYPTION_KEY (python -m scripts.backup_db --make-key).")
        return final
    encrypted = final.with_name(final.name + ".enc")
    tmp = encrypted.with_name(encrypted.name + ".partial")
    encrypt_file(partial, tmp, key)
    partial.unlink()
    tmp.replace(encrypted)
    return encrypted


def _add_search_stores(zf: zipfile.ZipFile) -> list[str]:
    added = []
    lexical = Path(settings.LEXICAL_DB_PATH or BACKEND / "lexical.db")
    if lexical.exists():
        _sqlite_copy(lexical, zf, "stores/lexical.db")
        added.append("stores/lexical.db")
    chroma = BACKEND / "chroma_db"
    if chroma.is_dir():
        for path in sorted(chroma.rglob("*")):
            if path.is_file():
                arc = "stores/chroma_db/" + path.relative_to(chroma).as_posix()
                if path.suffix == ".sqlite3":
                    _sqlite_copy(path, zf, arc)
                elif path.name.endswith(("-wal", "-shm", "-journal")):
                    continue  # folded into the .sqlite3 copy above
                else:
                    zf.write(path, arc)
                added.append(arc)
    print(f"  search stores: {len(added)} files")
    return added


def prune(keep: int, db_name: str, out_dir: Path | None = None, full: bool = False) -> list[Path]:
    """Delete all but the newest `keep` backups of this database, of one kind
    (daily, or "-full" with the search indexes), so neither crowds out the other."""
    out_dir = out_dir or backup_dir()
    zips = sorted((p for p in out_dir.glob(f"{db_name}-*.zip*")
                   if not p.name.endswith(".partial") and _kind_full(p) == full), key=lambda p: p.name)
    gone = zips[:-keep] if keep > 0 else []
    for path in gone:
        path.unlink()
    return gone


def copy_elsewhere(path: Path, copy_dir: Path, keep: int, db_name: str, full: bool) -> Path:
    """Copy a finished backup to a second location, and keep the same number there."""
    copy_dir.mkdir(parents=True, exist_ok=True)
    target = copy_dir / path.name
    partial = target.with_name(target.name + ".partial")
    shutil.copyfile(path, partial)
    partial.replace(target)
    if keep:
        prune(keep, db_name, copy_dir, full=full)
    return target


def run_scheduled(full: bool) -> dict:
    """What the server runs on its schedule (scheduled_tasks.py). Returns a summary."""
    keep = int(getattr(settings, "BACKUP_FULL_KEEP" if full else "BACKUP_KEEP", 2 if full else 14) or 0)
    path = backup(settings.DB_NAME, with_indexes=full)
    removed = prune(keep, settings.DB_NAME, full=full)
    summary = {"file": str(path), "mb": round(path.stat().st_size / 1e6, 1), "removed": len(removed)}
    copy_dir = getattr(settings, "BACKUP_COPY_DIR", "") or ""
    if copy_dir:
        summary["copy"] = str(copy_elsewhere(path, Path(copy_dir), keep, settings.DB_NAME, full))
    return summary


def restore(archive: Path, into: str, drop: bool = False, live_ok: bool = False) -> dict:
    if into == settings.DB_NAME and not live_ok:
        sys.exit(f"Refusing to restore into the live database {into!r}. Restore into a new name, "
                 f"or add --i-mean-the-live-db.")
    client = _client()
    db = client[into]
    existing = [n for n in db.list_collection_names() if not n.startswith("system.")]
    if existing and not drop:
        sys.exit(f"{into!r} already holds {len(existing)} collections. Add --drop to replace them.")
    if archive.name.endswith(".enc"):
        key = _key()
        if key is None:
            sys.exit("This backup is encrypted: set BACKUP_ENCRYPTION_KEY to the key it was made with.")
        plain = Path(tempfile.mkdtemp()) / archive.name[: -len(".enc")]
        try:
            decrypt_file(archive, plain, key)
        except Exception as e:  # noqa: BLE001
            sys.exit(f"Could not decrypt {archive.name}: wrong key, or the file is damaged ({type(e).__name__}).")
        archive = plain
    with zipfile.ZipFile(archive) as zf:
        manifest = json_util.loads(zf.read("manifest.json"))
        if manifest.get("format") != FORMAT:
            sys.exit(f"Unknown backup format {manifest.get('format')!r}.")
        if existing:
            client.drop_database(into)
        restored = {}
        for name, info in manifest["collections"].items():
            batch, count = [], 0
            with zf.open(f"collections/{name}.jsonl") as fh:
                for line in fh:
                    batch.append(json_util.loads(line))
                    if len(batch) == 1000:
                        db[name].insert_many(batch, ordered=False)
                        count += len(batch)
                        batch = []
            if batch:
                db[name].insert_many(batch, ordered=False)
                count += len(batch)
            if count == 0:
                db.create_collection(name)
            for spec in info.get("indexes", []):
                keys = [tuple(k) for k in spec.pop("keys")]
                db[name].create_index(keys, **spec)
            if count != info["count"]:
                sys.exit(f"{name}: restored {count} documents, the backup holds {info['count']}.")
            restored[name] = count
            print(f"  {name:<28} {count:>8} documents")
        if manifest.get("uploads"):
            target = Path(tempfile.mkdtemp(prefix="restored_uploads_", dir=BACKEND))
            for arc in manifest["uploads"]:
                zf.extract(arc, target)
            print(f"  {len(manifest['uploads'])} uploaded files extracted to {target / 'uploads'} "
                  f"(copy them into backend/uploads)")
        if manifest.get("files"):
            target = Path(tempfile.mkdtemp(prefix="restored_stores_", dir=BACKEND))
            for arc in manifest["files"]:
                zf.extract(arc, target)
            print(f"  search stores extracted to {target / 'stores'} (copy them into place with the server stopped)")
    return restored


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=settings.DB_NAME, help="database to back up (default: DB_NAME)")
    ap.add_argument("--with-indexes", action="store_true", help="also back up chroma_db and lexical.db")
    ap.add_argument("--keep", type=int, default=0, help="after backing up, keep only the newest N backups")
    ap.add_argument("--copy-to", type=Path, default=None,
                    help="also copy the backup here (default: BACKUP_COPY_DIR), keeping --keep there too")
    ap.add_argument("--restore", type=Path, help="a backup (.zip or .zip.enc) to restore")
    ap.add_argument("--make-key", action="store_true", help="print a new BACKUP_ENCRYPTION_KEY and exit")
    ap.add_argument("--into", help="database to restore into (required with --restore)")
    ap.add_argument("--drop", action="store_true", help="replace what the --into database holds")
    ap.add_argument("--i-mean-the-live-db", dest="live_ok", action="store_true")
    args = ap.parse_args()

    if args.make_key:
        print(make_key())
        print("Put it in the server's .env as BACKUP_ENCRYPTION_KEY=..., and keep a copy OFF the server.",
              file=sys.stderr)
        return

    if args.restore:
        if not args.into:
            ap.error("--restore needs --into DATABASE")
        print(f"Restoring {args.restore} into {args.into!r}:")
        restored = restore(args.restore, args.into, drop=args.drop, live_ok=args.live_ok)
        print(f"Restored {sum(restored.values())} documents in {len(restored)} collections.")
        return

    print(f"Backing up {args.db!r}:")
    path = backup(args.db, with_indexes=args.with_indexes)
    print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    if args.keep:
        for gone in prune(args.keep, args.db, full=args.with_indexes):
            print(f"  removed old backup {gone.name}")
    copy_dir = args.copy_to or (Path(settings.BACKUP_COPY_DIR) if getattr(settings, "BACKUP_COPY_DIR", "") else None)
    if copy_dir:
        print(f"Copied to {copy_elsewhere(path, copy_dir, args.keep, args.db, args.with_indexes)}")


if __name__ == "__main__":
    main()
