# PreviewGen Windows setup launcher.
# Downloads the latest published setup (or PREVIEWGEN_VERSION),
# checks its SHA-256 checksum, then opens the interactive Inno Setup wizard.
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo = "mustaqeem66/Freepik-Preview-Generator"
$TempDir = Join-Path $env:TEMP ("previewgen_setup_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

try {
    $ReleaseUrl = if ($env:PREVIEWGEN_VERSION) {
        "https://api.github.com/repos/$Repo/releases/tags/$($env:PREVIEWGEN_VERSION)"
    } else {
        "https://api.github.com/repos/$Repo/releases/latest"
    }

    $Release = Invoke-RestMethod -Uri $ReleaseUrl -Headers @{ "User-Agent" = "PreviewGen-Windows-Setup" }
    $SetupAsset = $Release.assets | Where-Object { $_.name -eq "PreviewGen-Setup.exe" } | Select-Object -First 1
    $ShaAsset = $Release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1
    if (-not $SetupAsset) { throw "The selected release does not contain PreviewGen-Setup.exe." }
    if (-not $ShaAsset) { throw "The selected release has no SHA256SUMS.txt; refusing an unverified install." }

    $SetupPath = Join-Path $TempDir "PreviewGen-Setup.exe"
    $ShaPath = Join-Path $TempDir "SHA256SUMS.txt"
    Write-Host "Downloading PreviewGen $($Release.tag_name) setup..."
    Invoke-WebRequest -Uri $SetupAsset.browser_download_url -OutFile $SetupPath -UseBasicParsing
    Invoke-WebRequest -Uri $ShaAsset.browser_download_url -OutFile $ShaPath -UseBasicParsing

    $HashLine = Get-Content -Path $ShaPath |
        Where-Object { $_ -match '^[A-Fa-f0-9]{64}\s+\*?PreviewGen-Setup\.exe\s*$' } |
        Select-Object -First 1
    if (-not $HashLine) { throw "SHA256SUMS.txt has no valid hash for PreviewGen-Setup.exe." }
    $ExpectedHash = ($HashLine -split '\s+')[0].ToLowerInvariant()
    $ActualHash = (Get-FileHash -Path $SetupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ExpectedHash -ne $ActualHash) {
        throw "SHA-256 verification failed for PreviewGen-Setup.exe. Installation cancelled."
    }

    Write-Host "SHA-256 verified. Opening the Windows setup wizard..."
    # Inno Setup handles install-path choice, optional desktop shortcut,
    # Start Menu entry, uninstaller and optional first launch.
    $SetupProcess = Start-Process -FilePath $SetupPath -Wait -PassThru
    if ($SetupProcess.ExitCode -ne 0) {
        throw "PreviewGen setup did not complete successfully (exit code $($SetupProcess.ExitCode))."
    }
    Write-Host "PreviewGen setup completed."
} finally {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}
