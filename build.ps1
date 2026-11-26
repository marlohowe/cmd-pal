$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "CMD Pal's executable build must run on Windows."
}

python -m pip install --disable-pip-version-check -r .\requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Force -Path .\build | Out-Null
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name CMD-Pal `
    --distpath .\dist `
    --workpath .\build\work `
    --specpath .\build `
    .\CMD_Pal.py

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Built .\dist\CMD-Pal.exe with no attached console window."
