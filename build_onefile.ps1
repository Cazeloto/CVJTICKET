$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Flet = Join-Path $ProjectRoot ".venv\Scripts\flet.exe"
$FletWeb = Join-Path $ProjectRoot ".venv\Lib\site-packages\flet_web\web"
$DistDir = Join-Path $ProjectRoot "dist_onefile"

if (-not (Test-Path -LiteralPath $Flet)) {
    throw "Ambiente virtual nao encontrado em .venv"
}

& $Flet pack run.py `
    -n CVJTICKET `
    --distpath $DistDir `
    --debug-console true `
    --add-data "assets:assets" `
    --add-data "db:db" `
    --add-data ".env:." `
    --add-data "${FletWeb}:flet_web\web" `
    --pyinstaller-build-args=--exclude-module=flet_desktop `
    -y

Write-Host ""
Write-Host "Executavel unico gerado em: $DistDir\CVJTICKET.exe"
