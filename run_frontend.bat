@echo off
echo ====================================================
echo Starting Legal Hybrid RAG Frontend (Port 5173)...
echo ====================================================
cd /d "%~dp0frontend"
npm run dev
pause
