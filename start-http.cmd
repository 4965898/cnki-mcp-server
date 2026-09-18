@echo off
chcp 65001 >nul
title CNKI MCP HTTP Service (port 37777)
echo ============================================================
echo  CNKI MCP Server - HTTP (streamable) mode
echo  Endpoint: http://127.0.0.1:37777/mcp
echo  Keep this window open. Close it to stop the service.
echo ============================================================
echo.

"C:\Users\Administrator\.workbuddy\binaries\python\envs\cnki\Scripts\python.exe" -m cnki_mcp serve-http --host 127.0.0.1 --port 37777

echo.
echo [Service stopped] Press any key to exit.
pause >nul
