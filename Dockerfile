FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim
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
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
