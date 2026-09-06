@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe scripts\race_server.py
if errorlevel 1 pause
