# ==============================================================================
# PreviewGen - Windows Installer
# ==============================================================================
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo = "Mustaqeem66/Freepik-Preview-Generator"
$AppName = "PreviewGen"
$InstallDir = "$env:LOCALAPPDATA\Programs\$AppName"
$TempDir = Join-Path $env:TEMP ("previewgen_install_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

try {
    $ReleaseUrl = if ($env:PREVIEWGEN_VERSION) {
        "https://api.github.com/repos/$Repo/releases/tags/$($env:PREVIEWGEN_VERSION)"
    } else {
        "https://api.github.com/repos/$Repo/releases/latest"
    }

    $Release = Invoke-RestMethod -Uri $ReleaseUrl -UseBasicParsing
    $ZipAsset = $Release.assets | Where-Object { $_.name -eq "PreviewGen-Windows.zip" } | Select-Object -First 1
    $ShaAsset = $Release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1

    if (-not $ZipAsset) {
        throw "Could not locate PreviewGen-Windows.zip in the release."
    }

    $ZipPath = Join-Path $TempDir "PreviewGen-Windows.zip"
    Invoke-WebRequest -Uri $ZipAsset.browser_download_url -OutFile $ZipPath -UseBasicParsing

    if ($ShaAsset) {
        $ShaPath = Join-Path $TempDir "SHA256SUMS.txt"
        Invoke-WebRequest -Uri $ShaAsset.browser_download_url -OutFile $ShaPath -UseBasicParsing
        $ShaContent = Get-Content $ShaPath
        $MatchingLine = $ShaContent | Where-Object { $_ -match "PreviewGen-Windows.zip" } | Select-Object -First 1
        if ($MatchingLine) {
            $Expected = ($MatchingLine -split "\s+")[0].Trim().ToLowerInvariant()
            $Actual = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($Expected -ne $Actual) {
                throw "SHA-256 checksum mismatch for PreviewGen-Windows.zip. Expected: $Expected, Got: $Actual"
            }
            Write-Host "Verified SHA-256 checksum."
        }
    }

    if (Test-Path $InstallDir) {
        Get-Process -Name $AppName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
        Remove-Item -Path $InstallDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $InstallDir -Force

    $ExePath = Join-Path $InstallDir "$AppName.exe"
    if (-not (Test-Path $ExePath)) {
        $Nested = Get-ChildItem -Path $InstallDir -Filter "$AppName.exe" -Recurse | Select-Object -First 1
        if ($Nested) { $ExePath = $Nested.FullName }
    }
    # Create Windows Desktop and Start Menu Shortcuts
    try {
        $WshShell = New-Object -ComObject WScript.Shell
        $DesktopPath = [Environment]::GetFolderPath("Desktop")
        $ShortcutPath = Join-Path $DesktopPath "$AppName.lnk"
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $ExePath
        $Shortcut.WorkingDirectory = $InstallDir
        $Shortcut.Description = "PreviewGen Studio"
        $Shortcut.Save()
        Write-Host "Created Desktop shortcut: $ShortcutPath"

        $ProgramsPath = [Environment]::GetFolderPath("Programs")
        $StartMenuPath = Join-Path $ProgramsPath "$AppName.lnk"
        $StartShortcut = $WshShell.CreateShortcut($StartMenuPath)
        $StartShortcut.TargetPath = $ExePath
        $StartShortcut.WorkingDirectory = $InstallDir
        $StartShortcut.Description = "PreviewGen Studio"
        $StartShortcut.Save()
        Write-Host "Created Start Menu shortcut: $StartMenuPath"
    } catch {
        Write-Warning "Could not create desktop shortcut: $_"
    }

    Write-Host "PreviewGen installed to $InstallDir"
} finally {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}
