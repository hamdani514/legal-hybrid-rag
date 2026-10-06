"""
Cross-encoder reranking — retrieval stage 3.5.

Why a reranker
--------------
The bi-encoder embeds the query and the passage independently and compares the
two vectors. That is what makes ANN search fast, and also what limits it: the
passage vector is built without ever seeing the query. Measured on this corpus,
the consequence is stark —

    mean cosine between sections WITHIN a judgment : 0.705
    mean cosine between sections ACROSS judgments  : 0.676

a separation of 0.029, with a score standard deviation of 0.069. 36% of queries
already have a top-1 vs top-2 margin under 0.02. At eleven judgments an
exhaustive scan still ranks correctly inside that margin; at a thousand, several
hundred irrelevant sections land in the same band and the ordering stops
meaning anything.

A cross-encoder reads the query and the passage together in one forward pass,
so it can tell that a passage about Family Court jurisdiction answers a question
about Family Court jurisdiction and a passage merely mentioning a Family Court
does not. It cannot be indexed — every pair costs a forward pass — which is why
it reranks a shortlist rather than replacing the search.

Which cross-encoder, and why the small one
------------------------------------------
Measured on the 20-query labelled set over 11 judgments, on 16 CPU cores, with
identical candidates and identical tie handling:

    no rerank                    p@1 0.650   MRR 0.817       151ms
    BAAI/bge-reranker-base       p@1 0.600   MRR 0.771    16,953ms
    ms-marco-MiniLM-L-6-v2       p@1 0.850   MRR 0.917     2,397ms

The 22M-parameter model beats the 278M one on accuracy and is seven times
faster. That inverts the usual expectation, so it is worth saying why: on this
corpus bge-reranker-base returns every candidate in a narrow band of negative
logits (-10.2 to -4.6 on a real query), meaning it judges all of them roughly
equally irrelevant, and an ordering drawn from that band is close to noise.
MiniLM is trained on MS MARCO passage ranking — find the passage that answers
this question — which is precisely the task here.

This is a finding about this corpus at this size, not a general law. Re-measure
with `eval/run_eval.py --reranker <name> --compare` as the corpus grows; a
larger cross-encoder may well earn its cost once there are thousands of
candidates to tell apart.

Failure behaviour
-----------------
Reranking is an improvement, not a dependency. If the model cannot be loaded —
not downloaded, out of memory, disabled by configuration — this module logs once
and returns the candidates in bi-encoder order. A query answered slightly worse
beats a query that raises.

Judgment-level reranking (precision v2)
---------------------------------------
`rerank()` scores the top 40 CHUNKS of the whole corpus. At 3,000 judgments
(~36,500 chunks) roughly 230 chunks outscore the right one, so the right case
never enters that window. `rerank_judgments()` is the replacement used by
app.retrieval.pipeline_v2: fusion first narrows the corpus to ~30 JUDGMENTS,
each contributes its best <=3 passages, and a judgment's relevance is the MAX
sigmoid(logit) over its passages. The window is now counted in cases, not in
chunks, so it does not shrink as the corpus grows. `rerank()` is unchanged and
still serves the live orchestrator.

Two backends: torch and ONNX int8
---------------------------------
RERANKER_BACKEND = "torch" (default) | "onnx". The ONNX backend runs a
dynamically-quantised int8 export of the same MiniLM (built by
`python -m app.retrieval.reranker --export-onnx`, written to
backend/models/reranker-onnx/). It exists because the cross-encoder is the
dominant CPU cost of a search once it sees ~90 pairs. It is only worth using if
it orders candidates the way torch does, so the export is accepted only when its
logits correlate with torch's at Spearman >= 0.98 on real candidate sets; see
the handoff numbers. If the ONNX file or onnxruntime is missing, scoring falls
back to torch with one log line — never to "no reranking".

Concurrency
-----------
Model loads (torch and ONNX) happen behind a lock: the lazy properties used to
be unguarded, so a search arriving during start-up warm-up loaded a second copy
of the model in parallel. Every scoring call takes one of the process-wide
inference slots from app.embeddings.embedding_generator, so concurrent
searches queue for the CPU instead of each spreading over every core (the
torch thread count is set there once, for the whole process).
"""

import math
import sys
import threading
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from app.config import settings

# Key under which a candidate carries its raw cross-encoder score.
RERANK_SCORE_KEY = "rerank_score"

# Key under which it carries that score mapped onto 0..1 for display.
RELEVANCE_KEY = "relevance"

# Key holding the text the cross-encoder should read.
TEXT_KEY = "text"


class Reranker:
    """Lazily-loaded CrossEncoder singleton.

    Mirrors app.embeddings.embedding_generator.EmbeddingGenerator: the model is
    heavy, so it loads once per process on first use rather than at import.
    """

    _instance = None
    _load_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._load_lock:
                if not cls._instance:
                    instance = super().__new__(cls)
                    instance._model = None
                    instance._unavailable = False
                    cls._instance = instance
        return cls._instance

    @property
    def model(self):
        """The CrossEncoder, or None if it could not be loaded."""
        if self._unavailable:
            return None
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is None and not self._unavailable:
                try:
                    import torch
                    from sentence_transformers import CrossEncoder

                    from app.embeddings.embedding_generator import cpu_policy

                    cpu_policy()  # thread count fixed before the first forward pass
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                    name = settings.RERANKER_MODEL
                    logger.info(f"Loading CrossEncoder {name!r} on {device}...")
                    self._model = CrossEncoder(name, device=device, max_length=512)
                    logger.info("CrossEncoder loaded.")
                except Exception as e:
                    # Latch the failure so a missing model costs one log line, not
                    # one failed download attempt per query.
                    self._unavailable = True
                    logger.error(f"Reranker unavailable, falling back to bi-encoder order: {e}")
                    return None

        return self._model

    def score(self, query: str, passages: list[str]) -> list[float] | None:
        """Score each passage against the query (raw logits). None when unavailable.

        Dispatches on RERANKER_BACKEND, read at call time so the evaluation can
        flip it. The ONNX path falls back to torch if it cannot run.
        """
        if not passages:
            return None
        if backend() == "onnx":
            # Load outside the slot (it is slow and lock-guarded), score inside it.
            if _onnx.ensure_loaded():
                from app.embeddings.embedding_generator import inference_slot

                with inference_slot():
                    scores = _onnx.score(query, passages)
                if scores is not None:
                    return scores
        if self.model is None:
            return None
        from app.embeddings.embedding_generator import inference_slot

        with inference_slot():
            return self.score_torch(query, passages)

    def score_torch(self, query: str, passages: list[str]) -> list[float] | None:
        """The sentence-transformers path; the reference the ONNX export is checked against."""
        model = self.model
        if model is None or not passages:
            return None

        pairs = [(query, passage) for passage in passages]

        # Raw logits, not the default sigmoid. bge-reranker's sigmoid saturates
        # hard at the low end — measured on a real query, 29 of 40 candidates
        # came back under 1e-4 and only 22 of 40 scores were distinct, so 18
        # candidates tied and then sorted arbitrarily. The logits carry the
        # same ordering (Spearman 1.0000) with 36 of 40 distinct, so this is
        # strictly more information for free.
        # sentence-transformers renamed this argument; try the current spelling
        # first, then the old one, then give up on logits and take the squashed
        # scores, which rank identically but with ties.
        import torch

        identity = torch.nn.Identity()
        scores = None
        for attempt in (
            lambda: model.predict(pairs, show_progress_bar=False, activation_fn=identity),
            lambda: model.predict(pairs, show_progress_bar=False, activation_fct=identity),
            lambda: model.predict(pairs, show_progress_bar=False),
        ):
            try:
                scores = attempt()
                break
            except TypeError:
                continue
            except Exception as e:
                logger.error(f"Reranking failed, keeping bi-encoder order: {e}")
                return None

        if scores is None:
            logger.error("Reranking produced no scores; keeping bi-encoder order.")
            return None

        try:
            return [float(s) for s in scores]
        except Exception as e:
            logger.error(f"Reranking failed, keeping bi-encoder order: {e}")
            return None


def _sigmoid(x: float) -> float:
    """Map a cross-encoder logit onto 0..1, saturating safely at the extremes."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    # exp(-x) overflows for very negative x; this form does not.
    e = math.exp(x)
    return e / (1.0 + e)


# ── ONNX int8 backend ────────────────────────────────────────────────────────

BACKEND_TORCH = "torch"
BACKEND_ONNX = "onnx"

DEFAULT_ONNX_DIR = Path(__file__).resolve().parents[2] / "models" / "reranker-onnx"
ONNX_INT8_FILE = "model.int8.onnx"
ONNX_FP32_FILE = "model.fp32.onnx"
ONNX_MAX_LENGTH = 512
ONNX_BATCH = 16


def backend() -> str:
    """RERANKER_BACKEND, read at call time ("torch" unless set to "onnx")."""
    value = str(getattr(settings, "RERANKER_BACKEND", BACKEND_TORCH) or BACKEND_TORCH).lower()
    return BACKEND_ONNX if value == BACKEND_ONNX else BACKEND_TORCH


def onnx_dir() -> Path:
    """RERANKER_ONNX_DIR, or backend/models/reranker-onnx."""
    configured = getattr(settings, "RERANKER_ONNX_DIR", "") or ""
    return Path(configured) if configured else DEFAULT_ONNX_DIR


class OnnxCrossEncoder:
    """onnxruntime session over the int8 export, with the model's own tokenizer.

    Produces the same raw logits as Reranker.score_torch (one per pair), so every
    caller — rerank(), rerank_judgments(), the sigmoid relevance — is unchanged.
    """

    def __init__(self):
        self._session = None
        self._tokenizer = None
        self._unavailable = False
        self._loaded_from: Path | None = None
        self._lock = threading.Lock()

    def ensure_loaded(self) -> bool:
        """Load the session once, even when many threads ask at the same time."""
        with self._lock:
            return self._load()

    def _load(self) -> bool:
        directory = onnx_dir()
        if self._session is not None and self._loaded_from == directory:
            return True
        if self._unavailable and self._loaded_from == directory:
            return False
        self._loaded_from = directory
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer

            path = directory / ONNX_INT8_FILE
            if not path.exists():
                raise FileNotFoundError(f"{path} (run python -m app.retrieval.reranker --export-onnx)")
            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            threads = int(getattr(settings, "RERANKER_ONNX_THREADS", 0) or 0)
            if threads > 0:
                options.intra_op_num_threads = threads
            self._session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
            self._tokenizer = AutoTokenizer.from_pretrained(str(directory))
            self._input_names = {i.name for i in self._session.get_inputs()}
            self._unavailable = False
            logger.info(f"ONNX cross-encoder loaded from {path}")
            return True
        except Exception as e:
            self._session = None
            self._unavailable = True
            logger.error(f"ONNX reranker unavailable, using torch: {e}")
            return False

    def score(self, query: str, passages: list[str]) -> list[float] | None:
        if not passages or not self._load():
            return None
        try:
            import numpy as np

            # Sort by length so each batch pads to its own longest pair, not to
            # the longest pair overall — most of the int8 speed-up is wasted on
            # padding otherwise.
            order = sorted(range(len(passages)), key=lambda i: len(passages[i]))
            out = [0.0] * len(passages)
            for start in range(0, len(order), ONNX_BATCH):
                batch = order[start:start + ONNX_BATCH]
                enc = self._tokenizer(
                    [query] * len(batch), [passages[i] for i in batch],
                    padding=True, truncation=True, max_length=ONNX_MAX_LENGTH, return_tensors="np",
                )
                feeds = {k: v.astype(np.int64) for k, v in enc.items() if k in self._input_names}
                logits = self._session.run(None, feeds)[0]
                for i, value in zip(batch, logits.reshape(len(batch), -1)[:, 0]):
                    out[i] = float(value)
            return out
        except Exception as e:
            logger.error(f"ONNX reranking failed, using torch: {e}")
            return None


_onnx = OnnxCrossEncoder()


def export_onnx(out_dir: Path | None = None) -> Path:
    """Export the configured cross-encoder to ONNX and quantise it to int8.

    Build-time only. Needs the `onnx` package for quantisation (onnxruntime
    alone can RUN the result but not quantise it); install it wherever this is
    run, it is not needed at query time.
    """
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic
    out = Path(out_dir) if out_dir else onnx_dir()
    out.mkdir(parents=True, exist_ok=True)
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    # Eager attention: transformers 5's SDPA mask builder indexes tensor shapes
    # in a way the TorchScript tracer cannot follow (IndexError at export).
    tokenizer = AutoTokenizer.from_pretrained(settings.RERANKER_MODEL)
    hf_model = AutoModelForSequenceClassification.from_pretrained(
        settings.RERANKER_MODEL, attn_implementation="eager")
    hf_model.eval()

    class _Logits(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner

        def forward(self, input_ids, attention_mask, token_type_ids):
            return self.inner(input_ids=input_ids, attention_mask=attention_mask,
                              token_type_ids=token_type_ids).logits

    dummy = tokenizer(["what is the holding"] * 2, ["the appeal was dismissed", "costs"],
                      padding=True, return_tensors="pt")
    names = ["input_ids", "attention_mask", "token_type_ids"]
    fp32 = out / ONNX_FP32_FILE

    # transformers 5 builds the attention mask through masking_utils, which the
    # TorchScript tracer cannot follow (traced shapes arrive as tensors and take
    # a deprecated branch that indexes them). For an encoder the mask is just
    # "padding positions get -inf", so a plain additive mask is substituted for
    # the duration of the export. Parity with torch is asserted by the caller.
    import transformers.models.bert.modeling_bert as modeling_bert

    def _additive_mask(config=None, inputs_embeds=None, attention_mask=None, **_):
        if attention_mask is None:
            return None
        dtype = inputs_embeds.dtype if inputs_embeds is not None else torch.float32
        mask = attention_mask[:, None, None, :].to(dtype)
        return (1.0 - mask) * torch.finfo(dtype).min

    original_mask = modeling_bert.create_bidirectional_mask
    modeling_bert.create_bidirectional_mask = _additive_mask
    try:
        _export_traced(torch, _Logits(hf_model), dummy, names, fp32)
    finally:
        modeling_bert.create_bidirectional_mask = original_mask

    int8 = out / ONNX_INT8_FILE
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    tokenizer.save_pretrained(str(out))
    logger.info(f"Exported {settings.RERANKER_MODEL} -> {int8} ({int8.stat().st_size / 1e6:.1f} MB)")
    return int8


def _export_traced(torch, module, dummy, names, path: Path) -> None:
    with torch.no_grad():
        torch.onnx.export(
            module, tuple(dummy[n] for n in names), str(path),
            input_names=names, output_names=["logits"],
            dynamic_axes={**{n: {0: "batch", 1: "seq"} for n in names}, "logits": {0: "batch"}},
            opset_version=17, do_constant_folding=True, dynamo=False,
        )


_reranker = Reranker()


# ── Judgment-level reranking (pipeline v2) ───────────────────────────────────

# Stats of the last rerank_judgments call, for the latency report.
last_stats: dict = {}


def rerank_judgments(
    query: str,
    evidence: dict[str, list[dict]],
    text_key: str = TEXT_KEY,
) -> dict[str, dict] | None:
    """Cross-encode each judgment's evidence passages; relevance = max sigmoid.

    Args:
        query: The query text the cross-encoder reads.
        evidence: judgment_id -> its passages (dicts with `text_key`), already
            capped by the caller (pipeline v2 sends <=3 per judgment, <=30
            judgments). All pairs go through the model in one call.
        text_key: Which key holds the passage text.

    Returns:
        judgment_id -> {"logit", "relevance", "best"} where "best" is the
        passage that scored highest; None when reranking is disabled or the
        model is unavailable (the caller keeps its previous order). Each scored
        passage also gains scores["rerank"] / scores["relevance"] (the
        contract's keys) and the legacy flat rerank_score / relevance keys.
    """
    last_stats.clear()
    if not is_enabled():
        return None
    flat: list[tuple[str, dict]] = [
        (jid, passage) for jid, passages in evidence.items() for passage in passages
        if (passage.get(text_key) or "").strip()
    ]
    if not flat:
        return None

    started = time.perf_counter()
    scores = _reranker.score(query, [p[text_key] for _, p in flat])
    elapsed = (time.perf_counter() - started) * 1000
    if scores is None:
        return None
    last_stats.update(pairs=len(flat), ms=elapsed, backend=backend(),
                      ms_per_pair=elapsed / len(flat))

    result: dict[str, dict] = {}
    for (jid, passage), logit in zip(flat, scores):
        relevance = _sigmoid(logit)
        passage.setdefault("scores", {})
        passage["scores"]["rerank"] = logit
        passage["scores"]["relevance"] = relevance
        passage[RERANK_SCORE_KEY] = logit
        passage[RELEVANCE_KEY] = relevance
        current = result.get(jid)
        if current is None or logit > current["logit"]:
            result[jid] = {"logit": logit, "relevance": relevance, "best": passage}
    logger.info(f"Judgment rerank: {len(flat)} pairs over {len(result)} judgments "
                f"in {elapsed:.0f}ms ({backend()})")
    return result


def is_enabled() -> bool:
    """Whether reranking is switched on. The evaluation harness flips this."""
    return bool(settings.RERANK_ENABLED)


def rerank(
    query: str,
    candidates: list[dict],
    top_n: int | None = None,
    text_key: str = TEXT_KEY,
) -> list[dict]:
    """Reorder `candidates` by cross-encoder relevance to `query`.

    Args:
        query: The cleaned user query.
        candidates: Dicts each carrying the passage text under `text_key` and
            a bi-encoder ``score``.
        top_n: How many of the incoming candidates to rerank. Defaults to
            RERANK_CANDIDATES. Candidates beyond it keep their bi-encoder
            order and are appended after the reranked ones, so nothing is
            dropped — the shortlist is only reordered.
        text_key: Which key holds the passage text.

    Returns:
        The candidates, reranked ones first. Each reranked candidate gains a
        ``rerank_score``. Returns the input order unchanged when reranking is
        disabled or unavailable.
    """
    if not candidates:
        return []

    if not is_enabled():
        return candidates

    top_n = top_n or settings.RERANK_CANDIDATES
    shortlist = candidates[:top_n]
    remainder = candidates[top_n:]

    passages = [(c.get(text_key) or "") for c in shortlist]
    scores = _reranker.score(query, passages)

    if scores is None:
        return candidates

    for candidate, score in zip(shortlist, scores):
        candidate[RERANK_SCORE_KEY] = score

    # Logits map to 0..1 through the sigmoid the model was trained against.
    #
    # An earlier version min-maxed the shortlist instead. That was a mistake
    # with real consequences: min-max makes the best candidate 1.0 BY
    # CONSTRUCTION, so a query with no answer in the corpus still displayed a
    # judgment at "Relevance 100%". The scale has to be absolute for a score to
    # mean anything, and it has to mean something for abstention to be possible
    # at all.
    #
    # Sigmoid is comparable across queries: 0.91 is a real match everywhere,
    # 0.16 is a real miss everywhere.
    for candidate in shortlist:
        candidate[RELEVANCE_KEY] = _sigmoid(candidate[RERANK_SCORE_KEY])

    shortlist.sort(key=lambda c: c[RERANK_SCORE_KEY], reverse=True)

    logger.info(
        f"Reranked {len(shortlist)} candidates "
        f"(top score {shortlist[0][RERANK_SCORE_KEY]:.3f})"
    )
    return shortlist + remainder


if __name__ == "__main__":
    if "--export-onnx" in sys.argv:
        print(f"exported: {export_onnx()}")
        sys.exit(0)

    query = "Is a claim relating to dower within the jurisdiction of a Family Court?"

    # Deliberately ordered WRONG, as a weak bi-encoder would: the decoy shares
    # vocabulary with the query, the answer shares meaning.
    candidates = [
        {"text": "The Family Court Act 1964 was enacted to provide for the "
                 "establishment of Family Courts in the Province.", "score": 0.72},
        {"text": "The respondent was in exclusive possession and received Ijjara "
                 "from the tenants, and never pleaded non-payment of dower. The "
                 "dispute concerned wrong entries in the revenue record, which in "
                 "no way can be termed as a matter relating to dower, and the "
                 "Family Court therefore lacked jurisdiction.", "score": 0.69},
        {"text": "The appellant was sentenced to ten years rigorous imprisonment "
                 "under section 302 of the Pakistan Penal Code.", "score": 0.66},
    ]

    print(f"enabled: {is_enabled()}   model: {settings.RERANKER_MODEL}\n")
    print("before (bi-encoder order):")
    for c in candidates:
        print(f"  {c['score']:.3f}  {c['text'][:62]}...")

    out = rerank(query, [dict(c) for c in candidates])

    print("\nafter (cross-encoder order):")
    for c in out:
        rs = c.get(RERANK_SCORE_KEY)
        shown = f"{rs:+.3f}" if rs is not None else "  n/a "
        print(f"  {shown}  {c['text'][:62]}...")

    assert len(out) == len(candidates), "reranking dropped or duplicated a candidate"

    if out[0].get(RERANK_SCORE_KEY) is not None:
        # The dower passage answers the question; the Act passage only shares words.
        assert "no way can be termed" in out[0]["text"], (
            "the cross-encoder did not surface the passage that answers the question"
        )
        scores = [c[RERANK_SCORE_KEY] for c in out if RERANK_SCORE_KEY in c]
        assert scores == sorted(scores, reverse=True), "output is not sorted by rerank score"
        print("\nOK: reranker promoted the answering passage over the keyword match.")
    else:
        print("\nOK: reranker unavailable; fell back to bi-encoder order without raising.")

    # ── judgment-level scoring (pipeline v2) ────────────────────────────────
    evidence = {
        "dower-case": [dict(candidates[1]), dict(candidates[2])],
        "act-case": [dict(candidates[0])],
        "empty-case": [{"text": "   "}],
    }
    judged = rerank_judgments(query, evidence)
    if judged is not None:
        assert set(judged) == {"dower-case", "act-case"}, judged.keys()
        assert judged["dower-case"]["relevance"] > judged["act-case"]["relevance"]
        assert judged["dower-case"]["best"] is evidence["dower-case"][0], "best passage must be the dower one"
        assert all(0.0 <= v["relevance"] <= 1.0 for v in judged.values())
        assert evidence["dower-case"][0]["scores"]["relevance"] == judged["dower-case"]["relevance"]
        assert last_stats["pairs"] == 3, last_stats
        print(f"OK: rerank_judgments - relevance = max over passages, "
              f"{last_stats['pairs']} pairs, {last_stats['ms_per_pair']:.0f} ms/pair ({last_stats['backend']}).")

    # ── ONNX parity, only when the export exists ────────────────────────────
    if (onnx_dir() / ONNX_INT8_FILE).exists():
        texts = [c["text"] for c in candidates]
        torch_scores = _reranker.score_torch(query, texts)
        onnx_scores = _onnx.score(query, texts)
        assert onnx_scores is not None, "ONNX export present but unusable"
        rank = lambda xs: sorted(range(len(xs)), key=lambda i: -xs[i])
        assert rank(torch_scores) == rank(onnx_scores), (torch_scores, onnx_scores)
        print(f"OK: ONNX int8 orders the fixture like torch "
              f"(max |dlogit| {max(abs(a - b) for a, b in zip(torch_scores, onnx_scores)):.3f}).")
    else:
        print("(ONNX export absent; parity check skipped.)")
