FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# The frontend tests must pass before anything is built.
RUN npm test
RUN npm run build

# Same Python as the tested environment: requirements.txt pins versions
# (numpy 2.4, pandas 3, scikit-learn 1.8) that need 3.11 or newer.
FROM python:3.11-slim
WORKDIR /app

# System packages the ingestion stack needs. Without these the image builds
# cleanly and then dies on the first import:
#   libgl1 / libglib2.0-0 / libxcb1  OpenCV's shared libraries. The full
#       opencv-python wheel links against X11; requirements.txt now installs
#       opencv-python-headless instead, and these stay as insurance because a
#       transitive dependency (easyocr) can still pull the GUI wheel in.
#   tesseract-ocr   the OCR binary pytesseract calls through PATH
#   poppler-utils   pdftoppm/pdftocairo, used by pdf2image
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libxcb1 \
        tesseract-ocr \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# The AI models, built into the image (~600 MB): the embedding model and the
# reranker for search, and EasyOCR's models for scanned uploads. Before, every
# start downloaded them from Hugging Face; when that failed, the server came up
# and answered every search "no case found". Only the model names (config.py)
# and the fetch script are copied first, so this layer is rebuilt when those
# change, not on every code change.
ENV HF_HOME=/opt/models/hf
ENV EASYOCR_MODULE_PATH=/opt/models/easyocr
COPY backend/app/config.py ./backend/app/config.py
COPY backend/scripts/fetch_models.py ./backend/scripts/fetch_models.py
RUN cd backend && python -m scripts.fetch_models && python -m scripts.fetch_models --check
# From here on the models come only from the image, never the network.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./backend/static

WORKDIR /app/backend
# Render (and most hosts) assign the port through $PORT and fail the deploy
# with "no open ports detected" if the app binds a different one. Shell form so
# the variable is expanded; 8000 keeps local `docker run -p 8000:8000` working.
ENV PORT=8000
# Healthy only once search can actually run (models loaded, indexes present,
# database answering): /api/health answers 503 until then. Loading takes ~30 s.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=8)" || exit 1

# --workers 1, deliberately: the per-minute limits, the search queue
# (app/api/search_slots.py) and the search index files all belong to one
# process. Scale with a bigger machine (4+ GB, 4+ cores), not more workers.
# --proxy-headers: behind Render's (or any) proxy, take the client's address from
# X-Forwarded-For, so per-network sign-in limits apply per user, not to everyone.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
