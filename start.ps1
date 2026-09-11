$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
$ErrorActionPreference = "Continue"

function Write-Banner {
    Write-Host ""
    Write-Host "  ========================================" -ForegroundColor Magenta
    Write-Host "           Astro Dwarf" -ForegroundColor Cyan
    Write-Host "    Telescope control and scheduling" -ForegroundColor DarkCyan
    Write-Host "  ========================================" -ForegroundColor Magenta
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "  > $Message" -ForegroundColor Yellow
}

function Write-Ok {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Gray
}

function Write-Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "  ! $Message" -ForegroundColor Red
    Write-Host ""
}

Write-Banner
Write-Host "  This script prepares a private Python setup," -ForegroundColor White
Write-Host "  then opens the Astro Dwarf desktop app." -ForegroundColor White
Write-Host ""

$pythonCommand = $null
$pythonArguments = @()

Write-Step "Looking for Python 3.11 or newer..."
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = "py"
        $pythonArguments = @("-3")
    }
}

if (-not $pythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python -c "import sys; raise SystemExit(sys.version_info < (3, 11))" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = "python"
    }
}

if (-not $pythonCommand) {
    Write-Fail "Python 3.11 or newer was not found. Install Python, then run this script again."
    exit 1
}

Write-Ok "Found Python ($pythonCommand)."

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Write-Step "Checking the app's private Python folder..."
if (-not (Test-Path $venvPython)) {
    Write-Info "Creating it now. This only happens the first time."
    & $pythonCommand @pythonArguments -m venv (Join-Path $PSScriptRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Could not create the private Python folder."
        exit $LASTEXITCODE
    }
    Write-Ok "Private Python folder is ready."
} else {
    Write-Ok "Already set up. Skipping this step."
}

Write-Step "Checking the packages Astro Dwarf needs..."
& $venvPython -c "import sys, PySide6; from dwarf_python_api.lib.dwarf_utils import perform_read_camera_params_http_v3, perform_enter_astro_mode; raise SystemExit(sys.version_info < (3, 11))" 2>$null
if ($LASTEXITCODE -ne 0) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Fail "Git is needed for the first install. Install Git, then run this script again."
        exit 1
    }

    Write-Info "Installing packages. The first run can take a minute."
    & $venvPython -m pip install -e ".[device]"
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Package install failed. Check the messages above, then try again."
        exit $LASTEXITCODE
    }
    Write-Ok "Packages are installed."
} else {
    Write-Ok "Packages are already installed. Skipping this step."
}

Write-Host ""
Write-Step "Starting Astro Dwarf..."
Write-Info "The app window should open in a moment."
Write-Host ""
& $venvPython app.py
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Astro Dwarf closed with an error."
    exit $LASTEXITCODE
}
exit $LASTEXITCODE
