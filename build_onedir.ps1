$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Flet = Join-Path $ProjectRoot ".venv\Scripts\flet.exe"
$FletWeb = Join-Path $ProjectRoot ".venv\Lib\site-packages\flet_web\web"

if (-not (Test-Path $Python)) {
    throw "Ambiente virtual não encontrado em .venv"
}

& $Python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando PyInstaller..."
    & $Python -m pip install pyinstaller==6.20.0
}

& $Flet pack run.py `
    -D `
    -n CVJTICKET `
    --distpath dist `
    --debug-console true `
    --add-data "assets:assets" `
    --add-data "db:db" `
    --add-data ".env:." `
    --add-data "${FletWeb}:flet_web\web" `
    -y

$DistDir = Join-Path $ProjectRoot "dist\CVJTICKET"
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "assets") (Join-Path $DistDir "assets")
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "db") (Join-Path $DistDir "db")
Copy-Item -Force (Join-Path $ProjectRoot ".env") (Join-Path $DistDir ".env")

Write-Host ""
Write-Host "Executável gerado em: $DistDir\CVJTICKET.exe"
