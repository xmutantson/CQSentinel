; CQSentinel Inno Setup Installer Script
; Creates a Windows installer for CQSentinel
;
; Requirements:
;   - Inno Setup 6.0+ (https://jrsoftware.org/isinfo.php)
;   - Built executable in dist/CQSentinel/
;
; Usage:
;   1. Build executable: python scripts/build_windows.py
;   2. Compile this script with Inno Setup
;   3. Output: Output/CQSentinel-Setup.exe

#define MyAppName "CQSentinel"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "CQSentinel Development Team"
#define MyAppURL "https://github.com/xmutantson/CQSentinel"
#define MyAppExeName "CQSentinel.exe"

[Setup]
; Basic app info
AppId={{B8E7F8E3-1234-5678-9ABC-DEF012345678}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; Installation paths
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output
OutputDir=Output
OutputBaseFilename=CQSentinel-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes

; Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; UI
WizardStyle=modern
SetupIconFile=resources\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; License (optional)
; LicenseFile=LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Main executable and all dependencies
Source: "dist\CQSentinel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Documentation
Source: "README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "QUICKSTART.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "INSTALL.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "PROJECT_PLAN.md"; DestDir: "{app}\docs"; Flags: ignoreversion

; Models directory (may be empty initially)
Source: "models\README.md"; DestDir: "{app}\models"; Flags: ignoreversion

[Dirs]
; Create directories for user data
Name: "{userappdata}\CQSentinel"; Flags: uninsneveruninstall
Name: "{userappdata}\CQSentinel\logs"; Flags: uninsneveruninstall
Name: "{userappdata}\CQSentinel\models"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Quick Start Guide"; Filename: "{app}\docs\QUICKSTART.md"
Name: "{group}\Documentation"; Filename: "{app}\docs"

[Run]
; Option to run after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up log files on uninstall (optional, user may want to keep)
; Type: filesandordirs; Name: "{userappdata}\CQSentinel\logs"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;

  // Check if .NET is installed (if we ever need it)
  // For now, CQSentinel is pure Python bundled with PyInstaller
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create initial config if it doesn't exist
    if not FileExists(ExpandConstant('{userappdata}\CQSentinel\config.yaml')) then
    begin
      // Config will be created on first run
      MsgBox('CQSentinel installed successfully!' + #13#10 + #13#10 +
             'On first run, the application will:' + #13#10 +
             '1. Create configuration in %APPDATA%\CQSentinel' + #13#10 +
             '2. Download AI models (requires internet)' + #13#10 + #13#10 +
             'See Quick Start Guide for setup instructions.',
             mbInformation, MB_OK);
    end;
  end;
end;

[Messages]
; Custom messages
WelcomeLabel2=This will install [name/ver] on your computer.%n%nCQSentinel is an SSB Contest Band Scanner with AI Voice Recognition for amateur radio operators.%n%nIMPORTANT: You will need:%n- Hamlib (rigctld) for radio control%n- Active amateur radio license%n%nIt is recommended that you close all other applications before continuing.
