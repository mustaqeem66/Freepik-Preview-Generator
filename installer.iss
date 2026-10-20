; ==============================================================================
; PreviewGen - Inno Setup Script
; Generates standard Windows Setup Wizard (PreviewGen-Setup.exe)
; ==============================================================================

#define MyAppName "PreviewGen"
#ifndef MyAppVersion
#define MyAppVersion "2.1.2"
#endif
#define MyAppPublisher "ZenArtisan"
#define MyAppURL "https://github.com/Mustaqeem66/Freepik-Preview-Generator"
#define MyAppExeName "PreviewGen.exe"

[Setup]
; Unique AppId for update/uninstall recognition
AppId={{E6A78C52-3F91-4D90-BA12-88E29A105B99}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; User-level installation (installs to %LOCALAPPDATA%\Programs without requiring admin privileges)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableDirPage=no
UsePreviousAppDir=yes
AllowNoIcons=yes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
LicenseFile=LICENSE
SetupIconFile=app.ico
UninstallDisplayIcon={app}\app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
OutputDir=dist
OutputBaseFilename=PreviewGen-Setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\PreviewGen\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"; AppUserModelID: "PreviewGen.Studio"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
