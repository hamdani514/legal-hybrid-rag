"""
Use the AI models already on this machine without asking Hugging Face first.

Loading a model the normal way first asks huggingface.co whether a newer
version exists. Where the network cannot reach it (a phone hotspot whose DNS
fails, a firewall, no internet), the library does not fall back to the copy on
disk: it fails ("Cannot send a request, as the client has been closed"), and
the server starts with search "NOT ready". So `uvicorn main:app` broke on some
networks unless HF_HUB_OFFLINE=1 was typed in front of it.

prefer_local_models() sets that switch itself, but only when every model the
app needs is already downloaded: a fresh machine still downloads them the
first time. It must run before anything imports huggingface_hub or
transformers (they read the switch once, at import), so main.py calls it first.
A value set by hand (HF_HUB_OFFLINE=0 to force an update check, or the
Dockerfile's 1) is never overridden.
"""

from __future__ import annotations

import os
from pathlib import Path


def _hub_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    return Path(home) / "hub"


def is_downloaded(model: str, cache: Path | None = None) -> bool:
    """Is `model` ("BAAI/bge-base-en-v1.5") in the Hugging Face cache, with its
    config and weights?"""
    folder = (cache or _hub_cache()) / f"models--{model.replace('/', '--')}" / "snapshots"
    for snapshot in folder.glob("*") if folder.is_dir() else []:
        has_weights = any((snapshot / w).exists() for w in ("model.safetensors", "pytorch_model.bin"))
        if (snapshot / "config.json").exists() and has_weights:
            return True
    return False


def prefer_local_models() -> str:
    """Switch Hugging Face to offline when the app's models are on disk.
    Returns what it did, for the startup log."""
    if os.environ.get("HF_HUB_OFFLINE") not in (None, ""):
        return f"HF_HUB_OFFLINE={os.environ['HF_HUB_OFFLINE']} (set outside the app)"
    from app.config import settings
    models = [m for m in (settings.EMBEDDING_MODEL, settings.RERANKER_MODEL) if m]
    missing = [m for m in models if not is_downloaded(m)]
    if missing:
        return f"online: not downloaded yet, will download {', '.join(missing)}"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    return "offline: using the models already on this machine"
