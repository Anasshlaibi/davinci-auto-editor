# start_chat_server.ps1
# Starts the DaVinci Resolve MCP server in SSE mode (http://127.0.0.1:8000)
# and opens the local chat UI in your default browser.
#
# Usage: Right-click -> Run with PowerShell
#        Or from terminal: .\start_chat_server.ps1

$ErrorActionPreference = "Stop"

$RepoRoot   = $PSScriptRoot
$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
$ServerScript = Join-Path $RepoRoot "src\server.py"
$ChatUI     = Join-Path $RepoRoot "chat_ui\index.html"

# Fixed token so the UI doesn't need to change every restart.
# Change this to anything you like — keep it secret if on a shared machine.
$env:DAVINCI_MCP_TOKEN = "resolve-local-dev-token"
$env:DAVINCI_MCP_PORT  = "8000"
$env:DAVINCI_MCP_HOST  = "127.0.0.1"
$env:PYTHONUTF8        = "1"
$env:PYTHONIOENCODING  = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8


Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DaVinci Resolve MCP  —  Local Chat     " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Server  : http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "  Token   : $($env:DAVINCI_MCP_TOKEN)" -ForegroundColor Yellow
Write-Host "  Chat UI : $ChatUI" -ForegroundColor Green
Write-Host ""
Write-Host "Make sure DaVinci Resolve is running before sending messages." -ForegroundColor Magenta
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Gray
Write-Host ""

# Open the chat UI in the default browser (after a short delay so the server can start)
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process $using:ChatUI
} | Out-Null

# Start the MCP server (blocks until Ctrl+C)
& $VenvPython $ServerScript --transport streamable-http
