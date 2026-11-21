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
    $SigPath = Join-Path $TempDir "SHA256SUMS.txt.asc"
    Write-Host "Downloading PreviewGen $($Release.tag_name) setup..."
    Invoke-WebRequest -Uri $SetupAsset.browser_download_url -OutFile $SetupPath -UseBasicParsing
    Invoke-WebRequest -Uri $ShaAsset.browser_download_url -OutFile $ShaPath -UseBasicParsing

    # The checksum file is fetched from the same release as the artifact, so on
    # its own it proves only that the two files agree. Verify the detached
    # signature over the checksums against the published public key before
    # trusting any hash from it.
    $SigAsset = $Release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt.asc" } | Select-Object -First 1
    $KeyAsset = $Release.assets | Where-Object { $_.name -eq "previewgen-signing-key.asc" } | Select-Object -First 1
    if ($SigAsset -and $KeyAsset) {
        Invoke-WebRequest -Uri $SigAsset.browser_download_url -OutFile $SigPath -UseBasicParsing
        $KeyPath = Join-Path $TempDir "previewgen-signing-key.asc"
        Invoke-WebRequest -Uri $KeyAsset.browser_download_url -OutFile $KeyPath -UseBasicParsing

        $Gpg = Get-Command "gpg.exe" -ErrorAction SilentlyContinue
        if (-not $Gpg) { $Gpg = Get-Command "gpg" -ErrorAction SilentlyContinue }
        if (-not $Gpg) {
            throw "gpg is required to verify the release signature but was not found. Installation cancelled."
        }
        & $Gpg.Source --batch --import $KeyPath
        & $Gpg.Source --batch --verify $SigPath $ShaPath
        if ($LASTEXITCODE -ne 0) {
            throw "Release signature verification failed for SHA256SUMS.txt. Installation cancelled."
        }
        Write-Host "Release signature verified."
    } else {
        Write-Warning "This release publishes no detached signature; only the checksum could be verified."
    }

    $HashLine = Get-Content -Path $ShaPath |
        Where-Object { $_ -match '^[A-Fa-f0-9]{64}\s+\*?PreviewGen-Setup\.exe\s*$' } |
        Select-Object -First 1
    if (-not $HashLine) { throw "SHA256SUMS.txt has no valid hash for PreviewGen-Setup.exe." }
    $ExpectedHash = ($HashLine -split '\s+')[0].ToLowerInvariant()
    $ActualHash = (Get-FileHash -Path $SetupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ExpectedHash -ne $ActualHash) {
        throw "SHA-256 verification failed for PreviewGen-Setup.exe. Installation cancelled."
    }

    # A valid checksum does not prove who produced the file. Require the
    # installer's own Authenticode signature to chain to a trusted signer.
    $Authenticode = Get-AuthenticodeSignature $SetupPath
    if ($Authenticode.Status -eq "Valid" -and $Authenticode.SignerCertificate) {
        Write-Host "Installer Authenticode signature valid: $($Authenticode.SignerCertificate.Subject)"
    } else {
        Write-Warning "The installer has no valid Authenticode signature (status: $($Authenticode.Status)). Only the checksum was verified."
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
