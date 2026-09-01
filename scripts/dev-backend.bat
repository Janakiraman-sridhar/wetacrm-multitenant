@echo off
cd /d "D:\WeTa CRM\backend"
.venv\Scripts\python.exe -m uvicorn app.main:asgi_app --port 8000 --reload
