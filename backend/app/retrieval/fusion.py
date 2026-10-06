"""
Judgment-level fusion of the R1..R5 retriever lists (stage F of precision v2).

Why fuse to JUDGMENTS before reranking
--------------------------------------
The live pipeline reranks the top 40 CHUNKS of the whole corpus. At 3,000
judgments (~36,500 chunks) about 230 chunks outscore the right one, so the right
case never reaches the cross-encoder. Fusing each retriever's list down to
judgments first, and reranking the top ~30 judgments by their best passages,
makes the window a count of cases, which does not shrink as the corpus grows.

Why Reciprocal Rank Fusion
--------------------------
The retrievers score on incompatible scales: cosine (0.6-0.9), -bm25 (unbounded,
query-length dependent), exact-match constants (0.74-1.0). Any score-level blend
needs per-retriever normalisation that drifts with the corpus and the query.
RRF uses only ranks:

    rrf(j) = sum over retrievers r of  w_r / (k + rank_r(j))      k = 60

with rank_r(j) the 1-based position of judgment j in r's list after collapsing
it to judgments (a judgment sits where its best chunk sits; chunk lists and
card lists are then ranked on the same "n-th judgment" footing, otherwise a
chunk list with five chunks of one case ahead of the next would push that next
case down five places). k=60 is the value from Cormack et al. (2009) and is not
tuned here.

The retrievers are complementary — measured alone on 46 queries, bm25_chunks
hits 0.40 on paraphrase while bm25_cards/dense_cards hit 0.80, and the reverse
on entity queries — which is exactly the situation RRF rewards: a judgment
ranked well by two different kinds of evidence beats one ranked first by one.

Weights default to 1.0 each (FUSION_WEIGHTS, read at call time). They are NOT
fitted to dev: dev has 22 positives over 10 judgments, so any fitted weights
would memorise those ten cases.

Exact match is pinned, not fused — unless it is a narrative's party hit
-----------------------------------------------------------------------
An exact case-number hit (score 1.0) or a specific party-name hit on a short
query (0.74-0.9) is the answer the user named. Fusing it as one vote among five
would let a long passage that repeats "2014" outvote it, so those hits are
placed above every fused judgment, ordered by their exact score.

A party-name hit on a case DESCRIPTION is weaker evidence: a story mentions
people and bodies in passing, and two judgments may share a litigant. The
exact retriever marks those candidates ``pinned=False``; they are fused as an
ordinary "exact" vote (rank and FUSION_WEIGHTS["exact"]) and never pinned.
A candidate without the key is pinned, as before.

Outcome as a soft signal
------------------------
``apply_outcome_signal`` lets a narrative's Supreme Court outcome (Facets
.outcome_sc) nudge judgments whose case card records the same outcome: a bonus
of OUTCOME_VOTE_SHARE (0.25) of a first-place RRF vote. It is never a filter —
a card outcome is "unknown" for some judgments, and a user may misremember how
a case ended — and at a quarter of one vote it can only reorder judgments that
the retrievers already rate nearly equal. It does not count toward n_first.

Evidence
--------
Each fused judgment keeps the chunk candidates that contributed to it (with
their texts, deduplicated by vector id across retrievers and ordered by a
chunk-level RRF) and its card hits separately. `select_evidence` picks the <=3
passages the cross-encoder will read, optionally reserving a slot for a section
the query type prefers (issue -> ANALYSIS_RATIO / LEGAL_ISSUES, disposition ->
FINAL_ORDER, entity/citation -> HEADER_CORAM). That is a light evidence-selection
preference, not a score change: the judgment's relevance is still the max
cross-encoder score over whatever passages were chosen.
"""

import json
import sys
from pathlib import Path
from typing import TypedDict

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings
from app.retrieval.contracts import RETRIEVERS, Candidate

DEFAULT_K = 60
CARD_SECTION = "CARD"
EXACT_SOURCE = "exact"

# Which sections to reserve one evidence slot for, per query type.
SECTION_PREFERENCE: dict[str, tuple[str, ...]] = {
    "issue": ("ANALYSIS_RATIO", "LEGAL_ISSUES"),
    "statute": ("ANALYSIS_RATIO", "LEGAL_ISSUES"),
    "disposition": ("FINAL_ORDER",),
    "entity": ("HEADER_CORAM",),
    "citation": ("HEADER_CORAM",),
}


class FusedJudgment(TypedDict, total=False):
    judgment_id: str
    rrf: float
    pinned: bool                 # exact-match hit, placed above all fused results
    exact_score: float
    exact_reason: str
    ranks: dict[str, int]        # retriever -> 1-based judgment rank in its list
    evidence: list[Candidate]    # chunk passages, best first
    cards: list[Candidate]       # card-level hits (bm25_cards / dense_cards)
    heading: str


def fusion_k() -> float:
    return float(getattr(settings, "FUSION_K", DEFAULT_K) or DEFAULT_K)


def fusion_weights() -> dict[str, float]:
    """FUSION_WEIGHTS from settings (a dict or a JSON string); 1.0 for anything unset."""
    raw = getattr(settings, "FUSION_WEIGHTS", None)
    weights = {name: 1.0 for name in RETRIEVERS}
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"FUSION_WEIGHTS is not valid JSON, using 1.0 each: {raw!r}")
            raw = None
    if isinstance(raw, dict):
        for name, value in raw.items():
            try:
                weights[name] = float(value)
            except (TypeError, ValueError):
                pass
    return weights


def collapse(candidates: list[Candidate]) -> list[tuple[str, int, list[Candidate]]]:
    """One retriever's ranked list -> [(judgment_id, 1-based judgment rank, its candidates)].

    The input must be best-first (every retriever's contract). A judgment's rank
    is the position of its first (best) candidate among distinct judgments.
    """
    order: list[str] = []
    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        jid = candidate.get("judgment_id")
        if not jid:
            continue
        if jid not in grouped:
            grouped[jid] = []
            order.append(jid)
        grouped[jid].append(candidate)
    return [(jid, index + 1, grouped[jid]) for index, jid in enumerate(order)]


def _chunk_key(candidate: Candidate) -> str:
    return candidate.get("vector_id") or f"{candidate.get('mongo_doc_id')}::{candidate.get('chunk_index', 0)}"


def fuse(
    lists: dict[str, list[Candidate]],
    weights: dict[str, float] | None = None,
    k: float | None = None,
    mode: str = "rrf",
) -> list[FusedJudgment]:
    """Fuse retriever lists into one judgment ranking.

    Args:
        lists: retriever name -> its ranked candidates (missing/empty is fine).
        weights: per-retriever weights; defaults to FUSION_WEIGHTS / 1.0.
        k: the RRF constant; defaults to FUSION_K / 60.
        mode: "rrf" (the fusion), or "union" — the no-fusion control: dense
            order first, then judgments only other retrievers found, by their
            best rank. Exact hits are pinned in both modes.

    Returns:
        FusedJudgments, pinned exact hits first, then by descending rrf.
    """
    weights = weights or fusion_weights()
    k = fusion_k() if k is None else float(k)
    fused: dict[str, FusedJudgment] = {}
    chunk_rrf: dict[str, dict[str, float]] = {}       # jid -> chunk key -> chunk-level rrf
    chunk_obj: dict[str, dict[str, Candidate]] = {}

    def entry(jid: str) -> FusedJudgment:
        if jid not in fused:
            fused[jid] = FusedJudgment(judgment_id=jid, rrf=0.0, pinned=False, exact_score=0.0,
                                       exact_reason="", ranks={}, evidence=[], cards=[], heading="")
            chunk_rrf[jid], chunk_obj[jid] = {}, {}
        return fused[jid]

    for source, candidates in lists.items():
        if not candidates:
            continue
        weight = weights.get(source, 1.0)
        for jid, rank, group in collapse(candidates):
            item = entry(jid)
            item["ranks"][source] = rank
            if not item["heading"]:
                item["heading"] = next((c.get("heading") for c in group if c.get("heading")), "")
            if source == EXACT_SOURCE and any(c.get("pinned", True) for c in group):
                group = [c for c in group if c.get("pinned", True)]
                best = max(float(c.get("score") or 0.0) for c in group)
                if best > item["exact_score"]:
                    item["exact_score"] = best
                    item["exact_reason"] = group[0].get("reason", "")
                item["pinned"] = True
                continue
            item["rrf"] += weight / (k + rank)
            if source == EXACT_SOURCE:
                continue  # an unpinned party vote: no passage text to use as evidence
            for candidate in group:
                if candidate.get("section_type") == CARD_SECTION or not candidate.get("mongo_doc_id"):
                    item["cards"].append(candidate)
                    continue
                key = _chunk_key(candidate)
                # Chunk-level RRF orders a judgment's evidence: a passage two
                # retrievers both put high is better evidence than either alone.
                position = int(candidate.get("rank", 0)) + 1
                chunk_rrf[jid][key] = chunk_rrf[jid].get(key, 0.0) + weight / (k + position)
                chunk_obj[jid].setdefault(key, candidate)

    for jid, item in fused.items():
        ordered = sorted(chunk_rrf[jid].items(), key=lambda kv: -kv[1])
        evidence = []
        for key, score in ordered:
            candidate = chunk_obj[jid][key]
            candidate.setdefault("scores", {})
            candidate["scores"]["rrf"] = score
            evidence.append(candidate)
        item["evidence"] = evidence

    def best_rank(item: FusedJudgment) -> int:
        ranks = [r for s, r in item["ranks"].items() if s != EXACT_SOURCE]
        return min(ranks) if ranks else 10 ** 6

    if mode == "union":
        def union_key(item: FusedJudgment):
            dense_rank = item["ranks"].get("dense_chunks")
            return (0, dense_rank, item["judgment_id"]) if dense_rank else (1, best_rank(item), item["judgment_id"])
        rest = sorted((i for i in fused.values() if not i["pinned"]), key=union_key)
    else:
        rest = sorted((i for i in fused.values() if not i["pinned"]),
                      key=lambda i: (-i["rrf"], best_rank(i), i["judgment_id"]))
    pinned = sorted((i for i in fused.values() if i["pinned"]),
                    key=lambda i: (-i["exact_score"], -i["rrf"], i["judgment_id"]))
    return pinned + rest


OUTCOME_VOTE_SHARE = 0.25


def apply_outcome_signal(
    fused: list[FusedJudgment],
    outcome: str | None,
    card_outcomes: dict[str, str],
    k: float | None = None,
    share: float | None = None,
) -> list[FusedJudgment]:
    """Nudge judgments whose card outcome equals the query's SC outcome.

    Adds share * 1/(k+1) to their rrf (a fraction of one first-place vote) and
    re-sorts the unpinned judgments; pinned ones stay on top in their order.
    No outcome, or no card outcome, changes nothing. Returns a new list.
    """
    if not outcome or outcome == "unknown" or not fused:
        return list(fused)
    k = fusion_k() if k is None else float(k)
    share = OUTCOME_VOTE_SHARE if share is None else float(share)
    bonus = share / (k + 1)
    for item in fused:
        if not item.get("pinned") and card_outcomes.get(item["judgment_id"]) == outcome:
            item["rrf"] = item.get("rrf", 0.0) + bonus
            item["outcome_match"] = True  # type: ignore[typeddict-unknown-key]
    pinned = [i for i in fused if i.get("pinned")]
    position = {i["judgment_id"]: n for n, i in enumerate(fused)}
    rest = sorted((i for i in fused if not i.get("pinned")),
                  key=lambda i: (-i.get("rrf", 0.0), position[i["judgment_id"]]))
    return pinned + rest


def select_evidence(
    item: FusedJudgment,
    per_judgment: int = 3,
    preferred_sections: tuple[str, ...] = (),
    include_card: bool = False,
) -> list[Candidate]:
    """The <=per_judgment passages the cross-encoder reads for one judgment.

    Best-first by chunk-level RRF, one chunk per distinct node where possible
    (three chunks of the same ANALYSIS_RATIO say less than three sections). If
    `preferred_sections` is given and none of the chosen passages is from one of
    them, the last slot goes to the best preferred-section passage available.
    `include_card` adds the best card hit as an extra passage (case cards carry
    the headnote, which is the closest text to a plain-English paraphrase).
    """
    chunks = list(item.get("evidence") or [])
    chosen: list[Candidate] = []
    seen_nodes: set[str] = set()
    for candidate in chunks:
        if len(chosen) >= per_judgment:
            break
        node = candidate.get("mongo_doc_id", "")
        if node in seen_nodes:
            continue
        chosen.append(candidate)
        seen_nodes.add(node)
    for candidate in chunks:  # same node allowed when distinct nodes run out
        if len(chosen) >= per_judgment:
            break
        if candidate not in chosen:
            chosen.append(candidate)

    if preferred_sections and chosen and not any(
            c.get("section_type") in preferred_sections for c in chosen):
        preferred = next((c for c in chunks if c.get("section_type") in preferred_sections
                          and c not in chosen), None)
        if preferred is not None:
            if len(chosen) >= per_judgment:
                chosen[-1] = preferred
            else:
                chosen.append(preferred)

    if include_card:
        cards = [c for c in (item.get("cards") or []) if (c.get("text") or "").strip()]
        if cards:
            # dense_cards text is the readable card; bm25_cards text is "col: value" lines.
            cards.sort(key=lambda c: (c.get("source") != "dense_cards", int(c.get("rank", 0))))
            chosen.append(cards[0])
    return chosen


if __name__ == "__main__":
    logger.remove()

    def cand(jid, source, rank, node="", chunk=0, section="ANALYSIS_RATIO", score=0.5, text="t"):
        return Candidate(judgment_id=jid, source=source, rank=rank, mongo_doc_id=node,
                         vector_id=f"{node}::{chunk}" if node else f"card:{jid}", chunk_index=chunk,
                         section_type=section if node else CARD_SECTION, score=score,
                         text=f"{text} {jid} {node}", scores={})

    # collapse: judgment rank = position among distinct judgments.
    dense = [cand("A", "dense_chunks", 0, "a1"), cand("A", "dense_chunks", 1, "a2"),
             cand("A", "dense_chunks", 2, "a3"), cand("B", "dense_chunks", 3, "b1"),
             cand("C", "dense_chunks", 4, "c1")]
    assert [(j, r) for j, r, _ in collapse(dense)] == [("A", 1), ("B", 2), ("C", 3)]

    # B is second in dense but first in BM25 and in cards -> B wins under RRF.
    bm25 = [cand("B", "bm25_chunks", 0, "b1"), cand("C", "bm25_chunks", 1, "c2"),
            cand("A", "bm25_chunks", 2, "a1")]
    cards = [cand("B", "bm25_cards", 0), cand("A", "bm25_cards", 1)]
    out = fuse({"dense_chunks": dense, "bm25_chunks": bm25, "bm25_cards": cards})
    assert [i["judgment_id"] for i in out] == ["B", "A", "C"], [i["judgment_id"] for i in out]
    b = out[0]
    assert abs(b["rrf"] - (1 / 62 + 1 / 61 + 1 / 61)) < 1e-12, b["rrf"]
    assert b["ranks"] == {"dense_chunks": 2, "bm25_chunks": 1, "bm25_cards": 1}
    # Evidence: b1 is in both chunk lists, deduplicated, carries a chunk-level rrf.
    assert [c["vector_id"] for c in b["evidence"]] == ["b1::0"]
    assert b["evidence"][0]["scores"]["rrf"] > 0 and len(b["cards"]) == 1
    a = next(i for i in out if i["judgment_id"] == "A")
    assert a["evidence"][0]["vector_id"] == "a1::0", "a1 (in two lists) must lead A's evidence"
    print("OK: collapse, weighted RRF, evidence dedupe and ordering")

    # Weights: silencing bm25 and cards restores dense order.
    w = {"dense_chunks": 1.0, "bm25_chunks": 0.0, "bm25_cards": 0.0}
    assert [i["judgment_id"] for i in fuse({"dense_chunks": dense, "bm25_chunks": bm25,
                                           "bm25_cards": cards}, weights=w)] == ["A", "B", "C"]

    # Exact hits are pinned above everything, case number above party name.
    exact = [cand("C", "exact", 0, score=0.8), cand("D", "exact", 1, score=1.0)]
    out = fuse({"dense_chunks": dense, "bm25_chunks": bm25, "exact": exact})
    assert [i["judgment_id"] for i in out][:2] == ["D", "C"] and out[0]["pinned"] and out[1]["pinned"]
    assert not out[2]["pinned"] and out[0]["exact_score"] == 1.0
    print("OK: weights read; exact hits pinned (1.0 above 0.8) above fused results")

    # A narrative party hit (pinned=False) is a vote, not a pin.
    vote = [dict(cand("C", "exact", 0, score=0.9), pinned=False)]
    out = fuse({"dense_chunks": dense, "bm25_chunks": bm25, "exact": vote})
    c_item = next(i for i in out if i["judgment_id"] == "C")
    assert not any(i["pinned"] for i in out) and c_item["ranks"]["exact"] == 1, out
    assert abs(c_item["rrf"] - (1 / 63 + 1 / 62 + 1 / 61)) < 1e-12 and c_item["evidence"], c_item
    mixed = [cand("D", "exact", 0, score=1.0), dict(cand("C", "exact", 1, score=0.8), pinned=False)]
    out = fuse({"dense_chunks": dense, "exact": mixed})
    assert out[0]["judgment_id"] == "D" and out[0]["pinned"] and not any(i["pinned"] for i in out[1:])
    print("OK: unpinned (narrative party) exact hits fuse as a vote; case-number hits still pin")

    # Outcome soft signal: reorders near-ties only, never filters, pinned untouched.
    base = fuse({"dense_chunks": dense[:4], "bm25_chunks": [cand("B", "bm25_chunks", 0, "b1"),
                                                           cand("A", "bm25_chunks", 1, "a1")]})
    order = [i["judgment_id"] for i in base]
    assert order[:2] == ["A", "B"], order          # A: 1/61+1/62, B: 1/62+1/61 -> tie, best_rank
    nudged = apply_outcome_signal(base, "allowed", {"B": "allowed", "A": "dismissed"})
    assert [i["judgment_id"] for i in nudged][:2] == ["B", "A"] and len(nudged) == len(base)
    far = fuse({"dense_chunks": dense, "bm25_chunks": bm25, "bm25_cards": cards})   # B, A, C
    assert [i["judgment_id"] for i in apply_outcome_signal(far, "allowed", {"C": "allowed"})] == ["B", "A", "C"]
    assert apply_outcome_signal(far, None, {"C": "allowed"}) == far
    print("OK: outcome signal breaks near-ties, cannot overturn a clear fused order, never filters")

    # Union control: dense order, then judgments only others found.
    union = fuse({"dense_chunks": dense[:3], "bm25_chunks": bm25}, mode="union")
    assert [i["judgment_id"] for i in union] == ["A", "B", "C"], [i["judgment_id"] for i in union]

    # Empty input and empty lists.
    assert fuse({}) == [] and fuse({"dense_chunks": [], "bm25_chunks": []}) == []

    # Evidence selection: distinct nodes first, preferred section reserved, card optional.
    item = FusedJudgment(judgment_id="X", evidence=[
        cand("X", "dense_chunks", 0, "n1", 0), cand("X", "dense_chunks", 1, "n1", 1),
        cand("X", "dense_chunks", 2, "n2", 0), cand("X", "dense_chunks", 3, "n3", 0),
        cand("X", "dense_chunks", 4, "n4", 0, section="FINAL_ORDER")],
        cards=[cand("X", "bm25_cards", 0), cand("X", "dense_cards", 0)])
    picked = select_evidence(item, 3)
    assert [c["vector_id"] for c in picked] == ["n1::0", "n2::0", "n3::0"]
    picked = select_evidence(item, 3, preferred_sections=("FINAL_ORDER",))
    assert [c["vector_id"] for c in picked] == ["n1::0", "n2::0", "n4::0"]
    picked = select_evidence(item, 3, include_card=True)
    assert len(picked) == 4 and picked[-1]["source"] == "dense_cards"
    two = FusedJudgment(judgment_id="Y", evidence=[cand("Y", "dense_chunks", 0, "m1", 0),
                                                   cand("Y", "dense_chunks", 1, "m1", 1)])
    assert len(select_evidence(two, 3)) == 2, "falls back to same-node chunks when nodes run out"
    print("OK: union control, empty inputs, evidence selection (distinct nodes, preferred slot, card)")

    print(f"OK: default weights {fusion_weights()} k={fusion_k():.0f}")
