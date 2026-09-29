@echo off
cd /d "%~dp0"
set PLAYWRIGHT_BROWSERS_PATH=%~dp0pw-browsers
set CNKI_AUTO_INSTALL=1
set NO_PROXY=cnki.net,*.cnki.net
if not exist "%~dp0logs" mkdir "%~dp0logs"
"C:\Users\Administrator\.workbuddy\binaries\python\envs\cnki\Scripts\python.exe" -m cnki_mcp serve-http --host 0.0.0.0 --port 37777 >> "%~dp0logs\cnki-http.log" 2>&1
