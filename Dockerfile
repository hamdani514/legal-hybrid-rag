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

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./backend/static

WORKDIR /app/backend
# Render (and most hosts) assign the port through $PORT and fail the deploy
# with "no open ports detected" if the app binds a different one. Shell form so
# the variable is expanded; 8000 keeps local `docker run -p 8000:8000` working.
ENV PORT=8000
# --proxy-headers: behind Render's (or any) proxy, take the client's address from
# X-Forwarded-For, so per-network sign-in limits apply per user, not to everyone.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
