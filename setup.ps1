# capcut-clipper setup (Windows PowerShell 5.1+)
#   .\setup.ps1                 venv + dependencies + ffmpeg into bin\
#   .\setup.ps1 -RegisterMcp    also register the CapCut MCP server with Claude Code (user scope)
param([switch]$RegisterMcp)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    python -m venv .venv
}
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -e "mcp\capcut-mcp"
& $py -m pip install -r requirements.txt

# ffmpeg: reuse one already on PATH, otherwise ask for it.
New-Item -ItemType Directory -Force bin | Out-Null
if (-not (Test-Path "bin\ffmpeg.exe")) {
    $found = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($found) {
        Copy-Item $found.Source "bin\ffmpeg.exe"
        $probe = Join-Path (Split-Path $found.Source) "ffprobe.exe"
        if (Test-Path $probe) { Copy-Item $probe "bin\ffprobe.exe" }
        Write-Host "Copied ffmpeg from $($found.Source)"
    } else {
        Write-Warning "ffmpeg not found. Install it (winget install Gyan.FFmpeg) or drop ffmpeg.exe into $root\bin, then rerun."
    }
}

if ($RegisterMcp) {
    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claude) { Write-Warning "claude CLI not on PATH; skipping MCP registration."; }
    else {
        # No env block on purpose: on Windows it replaces the whole environment and the server dies.
        & $claude.Source mcp add capcut -s user -- $py -m capcut_mcp.server
    }
}

& $py -m clipper doctor
