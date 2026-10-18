@echo off
echo ====================================================
echo Starting Legal Hybrid RAG Project
echo ====================================================
start "Legal RAG Backend" cmd /k "cd /d "%~dp0backend" && call "..\venv\Scripts\activate.bat" && uvicorn main:app --host 127.0.0.1 --port 5000"
timeout /t 4 /nobreak >nul
start "Legal RAG Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"
timeout /t 2 /nobreak >nul
start http://localhost:5173
echo Both Backend and Frontend have been launched.
