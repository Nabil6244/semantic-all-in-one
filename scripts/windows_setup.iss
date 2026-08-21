; Inno Setup — packages the PyInstaller onedir into a single Setup.exe
; Build (from repo root, after pyinstaller VideoGenerator.spec):
;   iscc scripts/windows_setup.iss

#define MyAppName "Semantic YT Studio"
#define MyAppExeName "Semantic YT Studio.exe"
#define MyAppVersion "1.0.0"

[Setup]
AppId={{A8F3C2E1-9B47-4D6A-8E21-SEMANTICYTSTUDIO}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Semantic YT Studio
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Semantic-YT-Studio-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=assets\AppIcon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Semantic YT Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
