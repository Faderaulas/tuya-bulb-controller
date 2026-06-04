@echo off
REM Launch the Tuya Bulb Controller without a console window.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "controlador_lampada.py"
