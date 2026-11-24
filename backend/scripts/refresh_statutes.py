"""
Re-read every judgment's cited provisions with the current section reader.

Each case card's ``statutes`` list was extracted at ingestion with the section
reader of that time (app/retrieval/statutes.py), which missed lettered sections
("489-F", "22-A"), lists ("Sections 448/380 PPC", "u/s 302/34") and sections of
other Acts ("section 122 of the Income Tax Ordinance"). The Section filter, the
"sections" shown on a result and section-aware search all read that list, so a
judgment whose section was missed cannot be found by it.

This re-reads each judgment's text (its nodes in MongoDB) and ADDS what the
current reader finds. Nothing already in the list is removed: some lists were
read from text files that ingestion has since deleted.

    venv/Scripts/python.exe -m scripts.refresh_statutes                       # dry run: counts only, writes nothing
    venv/Scripts/python.exe -m scripts.refresh_statutes --into-copy legal_rag_statutes_test
        # copies case_cards into that scratch database and refreshes the copy there
    venv/Scripts/python.exe -m scripts.refresh_statutes --apply --i-mean-the-live-db
        # the live database, and the card rows of lexical.db (copied first)
    venv/Scripts/python.exe -m scripts.refresh_statutes --rollback backups/statutes_before_<time>.json --i-mean-the-live-db

--apply first writes every card's previous list to backups/statutes_before_<time>.json
(what --rollback restores) and copies lexical.db to lexical.db.before-statutes-<time>.
Run it with the backend stopped, then start the backend again.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402


PROVISION_PREFIXES = ("Section ", "Article ", "Order ")


def merged(old: list, new: list) -> list:
    """The old list, plus the provisions (sections, articles, orders) the
    current reader finds that it lacks. Named Acts are not added: the Act-name
    rule has not changed, and on node text it also catches sentence starts."""
    from app.retrieval.case_sections import canonical
    # Old entries in one spelling ("Section 377B PPC" -> "Section 377-B PPC"),
    # so the same section is not listed twice.
    out = list(dict.fromkeys(canonical(s) for s in (old or []) if isinstance(s, str)))
    out += [s for s in dict.fromkeys(canonical(s) for s in new) if s.startswith(PROVISION_PREFIXES) and s not in out]
    return out


async def compute() -> dict[str, dict]:
    """{judgment_id: {"old": [...], "new": [...]}} for every case card (reads only)."""
    from app.database import connect_db, db
    from app.ingestion.metadata_extractor import _clean_statutes, _flat, load_sources
    from app.retrieval.statutes import parse_statutes

    await connect_db(wait_s=15)
    cards = [c async for c in db.database.case_cards.find({}, {"_id": 0, "judgment_id": 1, "statutes": 1})]
    out: dict[str, dict] = {}
    for i, card in enumerate(cards, 1):
        jid = card["judgment_id"]
        src = await load_sources(jid)
        text = src["raw"] or "\n".join(src["sections"].values())
        fresh = _clean_statutes(parse_statutes(_flat(text))) if text else []
        out[jid] = {"old": card.get("statutes") or [], "new": merged(card.get("statutes") or [], fresh)}
        if i % 500 == 0:
            print(f"  read {i}/{len(cards)}", flush=True)
    return out


def report(changes: dict[str, dict]) -> int:
    changed = {j: c for j, c in changes.items() if c["new"] != c["old"]}
    added = sum(len(set(c["new"]) - set(c["old"])) for c in changed.values())
    print(f"cards: {len(changes)} | would change: {len(changed)} | provisions added: {added}")
    import collections
    kinds = collections.Counter(_kind(s) for c in changed.values() for s in set(c["new"]) - set(c["old"]))
    print("  added, by kind:", dict(kinds.most_common()))
    return len(changed)


_CODES = {"PPC", "CrPC", "CPC", "QSO", "CNSA", "ATA"}


def _kind(provision: str) -> str:
    parts = provision.split()
    if parts[0] != "Section" or len(parts) < 3:
        return parts[0]   # Article / Order / a named Act
    if "-" in parts[1]:
        return "lettered section (489-F ...)"
    return "section of a code" if parts[-1] in _CODES else "section of another Act"


def update_fts(cards: list[dict], path: Path) -> None:
    """Replace the card rows of these judgments in the keyword index."""
    from app.indexing.fts_index import CARD_COLUMNS, card_row, connect, ensure_schema
    conn = connect(path)
    try:
        ensure_schema(conn)
        with conn:
            for card in cards:
                conn.execute("DELETE FROM cards_fts WHERE judgment_id = ?", (card["judgment_id"],))
                placeholders = ", ".join("?" * (len(CARD_COLUMNS) + 1))
                conn.execute(f"INSERT INTO cards_fts ({', '.join(CARD_COLUMNS)}, judgment_id) "
                             f"VALUES ({placeholders})", card_row(card))
    finally:
        conn.close()


async def write(target_db: str, changes: dict[str, dict], fts_path: Path | None) -> None:
    from pymongo import UpdateOne
    from app.database import db
    coll = db.client[target_db].case_cards
    ops = [UpdateOne({"judgment_id": j}, {"$set": {"statutes": c["new"]}})
           for j, c in changes.items() if c["new"] != c["old"]]
    for i in range(0, len(ops), 500):
        await coll.bulk_write(ops[i:i + 500], ordered=False)
    print(f"updated {len(ops)} case cards in {target_db!r}")
    if fts_path is not None:
        ids = [j for j, c in changes.items() if c["new"] != c["old"]]
        cards = [c async for c in coll.find({"judgment_id": {"$in": ids}}, {"_id": 0})]
        await asyncio.to_thread(update_fts, cards, fts_path)
        print(f"updated {len(cards)} card rows in {fts_path}")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--into-copy", metavar="DB", help="copy case_cards to this scratch database and refresh it there")
    ap.add_argument("--apply", action="store_true", help="refresh the live database and lexical.db")
    ap.add_argument("--rollback", type=Path, help="restore the lists saved by an earlier --apply")
    ap.add_argument("--i-mean-the-live-db", dest="live_ok", action="store_true")
    args = ap.parse_args()

    from app.database import connect_db, db
    from app.indexing.fts_index import db_path

    if args.rollback:
        if not args.live_ok:
            sys.exit("--rollback writes to the live database: add --i-mean-the-live-db.")
        saved = json.loads(args.rollback.read_text(encoding="utf-8"))
        await connect_db(wait_s=15)
        changes = {j: {"old": None, "new": lists} for j, lists in saved.items()}
        await write(settings.DB_NAME, changes, db_path())
        return

    changes = await compute()
    n = report(changes)

    if args.into_copy:
        if args.into_copy == settings.DB_NAME:
            sys.exit("--into-copy must name a scratch database, not the live one.")
        copy = db.client[args.into_copy].case_cards
        await copy.drop()
        docs = [d async for d in db.database.case_cards.find({})]
        for i in range(0, len(docs), 1000):
            await copy.insert_many(docs[i:i + 1000])
        print(f"copied {len(docs)} case cards to {args.into_copy!r}")
        await write(args.into_copy, changes, None)
    elif args.apply:
        if not args.live_ok:
            sys.exit("--apply writes to the live database: add --i-mean-the-live-db.")
        if not n:
            print("nothing to change")
            return
        stamp = time.strftime("%Y%m%dT%H%M%S")
        saved = BACKEND / "backups" / f"statutes_before_{stamp}.json"
        saved.parent.mkdir(exist_ok=True)
        saved.write_text(json.dumps({j: c["old"] for j, c in changes.items() if c["new"] != c["old"]}),
                         encoding="utf-8")
        print(f"previous lists saved to {saved} (for --rollback)")
        fts = db_path()
        if fts.exists():
            shutil.copy2(fts, fts.with_name(f"{fts.name}.before-statutes-{stamp}"))
            print(f"lexical.db copied to {fts.name}.before-statutes-{stamp}")
        await write(settings.DB_NAME, changes, fts if fts.exists() else None)
    else:
        print("dry run: nothing written (--into-copy DB to try it on a copy, --apply to write)")


if __name__ == "__main__":
    asyncio.run(main())
