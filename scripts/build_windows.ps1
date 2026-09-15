param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

python -m PyInstaller --noconfirm --clean packaging/AIGrader.spec
Copy-Item packaging/PORTABLE_README.txt dist/AIGrader-Windows-x64/README.txt -Force

$ZipPath = "dist/AIGrader-v$Version-Windows-x64.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path dist/AIGrader-Windows-x64 -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Created $ZipPath"
