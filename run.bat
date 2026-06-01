@echo off
REM Launch the Tuya Bulb Controller without a console window.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "bulb_controller.py"
