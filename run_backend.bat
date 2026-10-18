@echo off
echo ====================================================
echo Starting Legal Hybrid RAG Backend (Port 5000)...
echo ====================================================
cd /d "%~dp0backend"
call "..\venv\Scripts\activate.bat"
uvicorn main:app --host 127.0.0.1 --port 5000 --reload
pause
