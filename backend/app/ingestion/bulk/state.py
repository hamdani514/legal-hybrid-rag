"""
Append-only local state for bulk ingestion, keyed by file_hash.

MongoDB is the source of truth for anything that reached the database: a
re-run dedupes against `documents.file_hash`, so a completed file is skipped
and an interrupted one (status extracting/parsing/...) is resumed. Two facts
never reach the database, mirroring upload_pdf, which writes no record for a
file it rejects:

* the pdf_id assigned to a scanned file BEFORE its OCR finishes. OCR runs
  before the DB records are written (a file that turns out not to be a
  judgment must leave no record), so if the run dies mid-OCR, the next run
  must reuse the same pdf_id to find extract()'s cached uploads/{pdf_id}.txt;
* rejections ("not a Supreme Court judgment"), so a re-run does not OCR
  page 1 of every rejected scan again.

JSONL, one event per line, flushed and fsynced per write: Ctrl-C or a hard
kill loses at most the line being written, and a torn last line is skipped on
load. The last event per hash wins.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.records: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue  # torn final line from a hard kill
                h = ev.get("file_hash")
                if h:
                    self.records.setdefault(h, {}).update(ev)

    def get(self, file_hash: str) -> dict:
        return self.records.get(file_hash, {})

    def record(self, file_hash: str, **fields) -> dict:
        ev = {"file_hash": file_hash, **fields,
              "ts": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            self.records.setdefault(file_hash, {}).update(ev)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        return self.records[file_hash]


if __name__ == "__main__":
    import tempfile

    p = Path(tempfile.mkdtemp()) / "state.jsonl"
    s = StateStore(p)
    s.record("h1", pdf_id="p1", status="assigned")
    s.record("h1", status="rejected", error="not a judgment")
    s.record("h2", pdf_id="p2", status="assigned")
    with open(p, "a", encoding="utf-8") as fh:
        fh.write('{"file_hash": "h3", "pdf_id": "torn')  # simulated hard kill
    s2 = StateStore(p)
    assert s2.get("h1") == {**s2.get("h1"), "pdf_id": "p1", "status": "rejected"}
    assert s2.get("h2")["pdf_id"] == "p2"
    assert s2.get("h3") == {}
    print("state self-check OK")
