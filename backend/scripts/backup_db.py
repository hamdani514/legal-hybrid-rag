"""
Back up the MongoDB database to one file, and restore it.

    cd backend
    venv/Scripts/python.exe -m scripts.backup_db                       # back up DB_NAME
    venv/Scripts/python.exe -m scripts.backup_db --with-indexes        # also the search stores
    venv/Scripts/python.exe -m scripts.backup_db --keep 14             # then keep the newest 14
    venv/Scripts/python.exe -m scripts.backup_db --restore FILE --into legal_rag_restored

A backup is a zip in backend/backups (BACKUP_DIR to change it) holding one
JSON-lines file per collection, in MongoDB's extended JSON so ObjectIds and
dates come back as they were, the collections' indexes, and a manifest with
the document counts. Users, chats, payments, case cards, judgment sections
and uploaded files' records are all collections, so all are included.

--with-indexes adds the search stores (backend/chroma_db and lexical.db,
about 1 GB). They can be rebuilt from the database, but that takes hours of
embedding, so keep a copy of them from time to time.

Restoring writes only into the database named by --into. A database that
already holds data is refused unless --drop is given, and the live database
(DB_NAME) also needs --i-mean-the-live-db. Restore into a new name, check it,
then point DB_NAME at it.

Run it on a schedule (cron, or Windows Task Scheduler) and copy the zips off
the server: a backup on the same disk does not survive the disk.

A backup holds every user's personal data. Keep it as private as the
database itself.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

from app.config import settings

BACKEND = Path(__file__).resolve().parents[1]
FORMAT = 1


def backup_dir() -> Path:
    return Path(os.getenv("BACKUP_DIR") or BACKEND / "backups")


def _client() -> MongoClient:
    return MongoClient(settings.MONGO_URL, serverSelectionTimeoutMS=10000)


def backup(db_name: str, with_indexes: bool = False, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or backup_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = out_dir / f"{db_name}-{stamp}.zip"
    partial = final.with_suffix(".zip.partial")  # never leave a half-written backup looking complete
    db = _client()[db_name]
    manifest = {"format": FORMAT, "database": db_name, "created_at": stamp, "collections": {}, "files": []}
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
        if with_indexes:
            manifest["files"] = _add_search_stores(zf)
        zf.writestr("manifest.json", json_util.dumps(manifest, indent=2))
    partial.replace(final)
    return final


def _add_search_stores(zf: zipfile.ZipFile) -> list[str]:
    added = []
    lexical = Path(settings.LEXICAL_DB_PATH or BACKEND / "lexical.db")
    if lexical.exists():
        # A consistent copy even while the server is writing to it.
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "lexical.db"
            src, dst = sqlite3.connect(lexical), sqlite3.connect(copy)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            zf.write(copy, "stores/lexical.db")
        added.append("stores/lexical.db")
    chroma = BACKEND / "chroma_db"
    if chroma.is_dir():
        for path in sorted(chroma.rglob("*")):
            if path.is_file():
                arc = "stores/chroma_db/" + path.relative_to(chroma).as_posix()
                zf.write(path, arc)
                added.append(arc)
    print(f"  search stores: {len(added)} files")
    return added


def prune(keep: int, db_name: str, out_dir: Path | None = None) -> list[Path]:
    """Delete all but the newest `keep` backups of this database."""
    out_dir = out_dir or backup_dir()
    zips = sorted(out_dir.glob(f"{db_name}-*.zip"))
    gone = zips[:-keep] if keep > 0 else []
    for path in gone:
        path.unlink()
    return gone


def restore(archive: Path, into: str, drop: bool = False, live_ok: bool = False) -> dict:
    if into == settings.DB_NAME and not live_ok:
        sys.exit(f"Refusing to restore into the live database {into!r}. Restore into a new name, "
                 f"or add --i-mean-the-live-db.")
    client = _client()
    db = client[into]
    existing = [n for n in db.list_collection_names() if not n.startswith("system.")]
    if existing and not drop:
        sys.exit(f"{into!r} already holds {len(existing)} collections. Add --drop to replace them.")
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
    ap.add_argument("--restore", type=Path, help="a backup zip to restore")
    ap.add_argument("--into", help="database to restore into (required with --restore)")
    ap.add_argument("--drop", action="store_true", help="replace what the --into database holds")
    ap.add_argument("--i-mean-the-live-db", dest="live_ok", action="store_true")
    args = ap.parse_args()

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
        for gone in prune(args.keep, args.db):
            print(f"  removed old backup {gone.name}")


if __name__ == "__main__":
    main()
