"""
Put the AI models the app needs into the Docker image, and prove they load offline.

    python -m scripts.fetch_models           # download (the Docker build runs this)
    python -m scripts.fetch_models --check   # load everything with the network off

Without this, every container start downloaded the models from Hugging Face
(anonymously, rate-limited). When that failed the server still started, search
returned nothing for every query, and nothing said so. Now the image holds:

  * the embedding model    settings.EMBEDDING_MODEL  (search and ingestion)
  * the reranker           settings.RERANKER_MODEL   (search)
  * the EasyOCR models     English detection + recognition (scanned uploads)

and the image runs with HF_HUB_OFFLINE=1, so it never tries the network.
Model names come from app/config.py, so changing a model there and rebuilding
bakes the new one; --check fails the build (CI) if what is configured is not
in the image.
"""

from __future__ import annotations

import os
import sys
import time


def main() -> int:
    check = "--check" in sys.argv
    if check:
        # Must be set before huggingface_hub is imported: it reads them once.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    from app.config import settings

    failed = []

    def step(label, load):
        started = time.perf_counter()
        try:
            load()
            print(f"  ok   {label} ({time.perf_counter() - started:.1f}s)")
        except Exception as e:  # noqa: BLE001
            failed.append(label)
            print(f"  FAIL {label}: {str(e).splitlines()[0][:200]}")

    print("Checking the models load with the network off:" if check else "Downloading models into the image:")

    def embedding():
        from sentence_transformers import SentenceTransformer
        SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu").encode("model check")

    def reranker():
        from sentence_transformers import CrossEncoder
        CrossEncoder(settings.RERANKER_MODEL, device="cpu", max_length=512).predict([("model check", "model check")])

    def ocr():
        import easyocr
        easyocr.Reader(["en"], gpu=False, download_enabled=not check, verbose=False)

    step(f"embedding model {settings.EMBEDDING_MODEL}", embedding)
    step(f"reranker {settings.RERANKER_MODEL}", reranker)
    step("EasyOCR English models", ocr)

    if failed:
        print(f"{len(failed)} model(s) unavailable: " + ", ".join(failed))
        return 1
    print("All models available.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
