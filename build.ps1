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

$executable = (Resolve-Path .\dist\CMD-Pal.exe).Path
$signingThumbprint = $env:CMDPAL_SIGNING_CERT_THUMBPRINT

if ([string]::IsNullOrWhiteSpace($signingThumbprint)) {
    Write-Warning "Built unsigned. Set CMDPAL_SIGNING_CERT_THUMBPRINT to sign with a trusted code-signing certificate installed in CurrentUser\My."
} else {
    $signingThumbprint = $signingThumbprint -replace '\s', ''
    if ($signingThumbprint -notmatch '^[0-9A-Fa-f]{40}$') {
        throw "CMDPAL_SIGNING_CERT_THUMBPRINT must be a 40-character certificate thumbprint."
    }

    $signToolPath = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
    if (-not $signToolPath) {
        $windowsKitsPath = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
        if (Test-Path $windowsKitsPath) {
            $signTool = Get-ChildItem $windowsKitsPath -Filter signtool.exe -Recurse -File |
                Where-Object { $_.Directory.Name -eq "x64" } |
                Sort-Object FullName -Descending |
                Select-Object -First 1
            if ($signTool) {
                $signToolPath = $signTool.FullName
            }
        }
    }
    if (-not $signToolPath) {
        throw "SignTool was not found. Install the Windows SDK or add signtool.exe to PATH."
    }

    & $signToolPath sign /sha1 $signingThumbprint /fd SHA256 `
        /tr https://timestamp.digicert.com /td SHA256 $executable
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool failed to sign CMD-Pal.exe."
    }

    & $signToolPath verify /pa /v $executable
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool could not verify the CMD-Pal.exe signature."
    }

    Write-Host "Built and Authenticode-signed .\dist\CMD-Pal.exe."
}

Write-Host "Built .\dist\CMD-Pal.exe with no attached console window."
