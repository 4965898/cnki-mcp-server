' CNKI MCP HTTP service silent launcher (for Windows Startup folder)
' Starts run-http-server.bat fully hidden (window style 0) and returns immediately.
Dim sh, batPath
batPath = "A:\Trae CN\repository\WorkBudddy\2026-09-18-16-38-55\cnki-mcp-server\run-http-server.bat"
Set sh = CreateObject("WScript.Shell")
sh.Run """" & batPath & """", 0, False
