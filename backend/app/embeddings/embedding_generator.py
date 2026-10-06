"""
The SentenceTransformer singleton, and the process-wide CPU policy for models.

Why the CPU policy lives here
-----------------------------
Every model this backend runs (the bi-encoder here, the cross-encoder in
app.retrieval.reranker) executes inside worker threads (``asyncio.to_thread``),
and by default each torch call spreads over every core it can find. Two
concurrent searches therefore ran two 8-thread GEMMs on 8 physical cores, ten
searches ran eighty threads, and latency grew far faster than the load —
everyone thrashed instead of queueing.

So this module, imported by everything that touches a model:

* sets ``torch.set_num_threads`` once (``TORCH_THREADS``; 0 = automatic, half
  the logical cores — on this 8-core/16-thread machine that is 8, torch's own
  single-request default, so one search is no slower than before);
* exposes :func:`inference_slot`, a bounded semaphore with
  ``MODEL_INFERENCE_CONCURRENCY`` slots (0 = automatic, logical cores divided
  by torch threads — 2 here). Every encode / predict takes a slot, so at most
  ``slots x threads`` = 16 compute threads exist however many searches arrive;
  the rest queue in arrival order, which is cheaper than oversubscribing;
* loads the model behind a lock. The lazy property used to be unguarded, so a
  search arriving during start-up warm-up loaded a second copy in parallel.

The model is wrapped at load time (``model.encode`` takes a slot), so callers
that use ``EmbeddingGenerator().model.encode(...)`` directly — the query
embedder, the chunker, the warm-up — are gated without changing them.
"""

import os
import threading
from contextlib import contextmanager
from functools import wraps

import torch
from loguru import logger
from sentence_transformers import SentenceTransformer

from app.config import settings

# Ingestion batches are split into sub-batches of this many texts, each taking
# its own inference slot, so an upload's embedding pass cannot hold a slot for
# the whole judgment while searches wait behind it.
INGEST_SLICE = 128

_policy_lock = threading.Lock()
_policy: dict | None = None
_slots: threading.BoundedSemaphore | None = None


def cpu_policy() -> dict:
    """Apply (once) and return {"torch_threads", "inference_slots", "cores"}."""
    global _policy, _slots
    if _policy is not None:
        return _policy
    with _policy_lock:
        if _policy is not None:
            return _policy
        cores = os.cpu_count() or 4
        threads = int(getattr(settings, "TORCH_THREADS", 0) or 0)
        if threads <= 0:
            threads = max(1, cores // 2)
        slots = int(getattr(settings, "MODEL_INFERENCE_CONCURRENCY", 0) or 0)
        if slots <= 0:
            slots = max(1, cores // threads)
        try:
            torch.set_num_threads(threads)
        except Exception as e:  # never fatal: torch keeps its default
            logger.warning(f"torch.set_num_threads({threads}) failed: {e}")
        _slots = threading.BoundedSemaphore(slots)
        _policy = {"torch_threads": torch.get_num_threads(), "inference_slots": slots, "cores": cores}
        logger.info(f"Model CPU policy: {_policy}")
        return _policy


# Applied at import: the first torch op anywhere in the process should already
# run with the chosen thread count.
cpu_policy()

_waiting = {"now": 0, "max": 0}
_waiting_lock = threading.Lock()


@contextmanager
def inference_slot():
    """Hold one of the process-wide model inference slots (blocking; use in threads)."""
    cpu_policy()
    with _waiting_lock:
        _waiting["now"] += 1
        _waiting["max"] = max(_waiting["max"], _waiting["now"])
    _slots.acquire()  # type: ignore[union-attr]
    with _waiting_lock:
        _waiting["now"] -= 1
    try:
        yield
    finally:
        _slots.release()  # type: ignore[union-attr]


def gated(fn):
    """Wrap a model call so it runs inside :func:`inference_slot`."""
    if getattr(fn, "_inference_gated", False):
        return fn

    @wraps(fn)
    def wrapper(*args, **kwargs):
        with inference_slot():
            return fn(*args, **kwargs)

    wrapper._inference_gated = True  # type: ignore[attr-defined]
    return wrapper


class EmbeddingGenerator:
    _instance = None
    _load_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._load_lock:
                if not cls._instance:
                    instance = super(EmbeddingGenerator, cls).__new__(cls)
                    instance._model = None
                    cls._instance = instance
        return cls._instance

    @property
    def model(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is None:  # another thread may have loaded it meanwhile
                device = "cuda" if torch.cuda.is_available() else "cpu"
                # The model is named once, in settings, because the ingestion and
                # query sides must embed into the same space. A mismatch produces
                # vectors that compare cleanly and mean nothing.
                model_name = settings.EMBEDDING_MODEL
                logger.info(f"Loading SentenceTransformer model {model_name!r} on {device}...")
                try:
                    model = SentenceTransformer(model_name, device=device)
                except Exception as e:
                    logger.error(f"Failed to load SentenceTransformer model: {e}")
                    raise
                model.encode = gated(model.encode)
                self._model = model
                logger.info("SentenceTransformer model loaded successfully.")
        return self._model

    def generate_embeddings(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []

        try:
            out: list[list[float]] = []
            model = self.model
            for start in range(0, len(texts), INGEST_SLICE):
                embeddings = model.encode(
                    texts[start:start + INGEST_SLICE],
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                out.extend(embeddings.tolist())
            return out
        except Exception as e:
            logger.error(f"Error during embedding generation: {e}")
            raise e


if __name__ == "__main__":
    import time
    from concurrent.futures import ThreadPoolExecutor

    policy = cpu_policy()
    assert policy["torch_threads"] >= 1 and policy["inference_slots"] >= 1, policy
    assert torch.get_num_threads() == policy["torch_threads"]

    # Twelve threads race the cold singleton: exactly one model may load.
    EmbeddingGenerator._instance = None
    loads = {"n": 0}
    real_init = SentenceTransformer.__init__

    def counting_init(self, *a, **k):
        loads["n"] += 1
        real_init(self, *a, **k)

    SentenceTransformer.__init__ = counting_init
    with ThreadPoolExecutor(12) as pool:
        models = list(pool.map(lambda _: EmbeddingGenerator().model, range(12)))
    SentenceTransformer.__init__ = real_init
    assert loads["n"] == 1, f"model loaded {loads['n']} times"
    assert all(m is models[0] for m in models)

    # Sixteen concurrent encodes never exceed the slot count.
    active = {"now": 0, "max": 0}
    lock = threading.Lock()
    inner = models[0].encode.__wrapped__

    def probe(*a, **k):
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        try:
            return inner(*a, **k)
        finally:
            with lock:
                active["now"] -= 1

    models[0].encode = gated(probe)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(16) as pool:
        vectors = list(pool.map(lambda i: models[0].encode(f"query number {i}"), range(16)))
    assert len(vectors) == 16 and vectors[0].shape[0] == settings.EMBEDDING_DIM
    assert active["max"] <= policy["inference_slots"], active
    print(f"policy {policy}; 16 concurrent encodes in {time.perf_counter() - t0:.2f}s, "
          f"max {active['max']} in flight, max {_waiting['max']} queued")
    assert len(EmbeddingGenerator().generate_embeddings(["a", "b", "c"])) == 3
    print("OK: one model load under a race; inference bounded by the slot count.")
