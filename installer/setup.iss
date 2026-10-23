; ============================================================================
;  Swept — installer (Inno Setup 6)
;
;  What it does: installs Swept into "Program Files", creates Start Menu
;  shortcuts and (optionally) a desktop one, registers itself in
;  "Apps & Features" and ships a proper uninstaller.
;
;  How to build:
;    1. Install Inno Setup 6 (once): https://jrsoftware.org/isdl.php
;    2. Compile the script from the project root:
;         "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\setup.iss
;       or open installer\setup.iss in Inno Setup and press Build -> Compile.
;
;  Result: dist\Swept-Setup-1.2.0.exe
;
;  Important: dist\Swept.exe must exist before compiling
;  (python build.py), otherwise compilation fails at the [Files] step.
; ============================================================================

#define MyAppName "Swept"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Vladvodex"
#define MyAppURL "https://github.com/vladcodex/swept"
#define MyAppExeName "Swept.exe"
; Application identifier: any unique GUID string. Must never change after the
; first release, otherwise Windows treats the installer as a different program.
#define MyAppId "7E2A9F31-4C6B-4D8E-A1F2-3B5C9D0E7A64"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright (c) 2026 {#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (c) 2026 {#MyAppPublisher}
VersionInfoDescription=Swept Setup
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Swept-Setup-{#MyAppVersion}
SetupIconFile=..\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 64-bit application.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Swept clears the system cache and updates policies, so it needs administrator
; rights — the .exe manifest requests the same.
PrivilegesRequired=admin
MinVersion=10.0

[Languages]
; The installer speaks the same two languages as the application itself.
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Desktop shortcut is opt-in, not the default.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The application is built as an "onedir" bundle (build.py --onedir): Swept.exe
; plus its _internal\ runtime live side by side in dist\Swept\. Copy the whole
; tree into {app}. Onedir (instead of a single onefile exe) is deliberate: a
; onefile exe unpacks itself into %TEMP%\_MEIxxxxx at launch, a drop-and-run
; pattern that trips AV heuristics (e.g. Microsoft Wacast). Onedir has no such
; self-extraction.
Source: "..\dist\Swept\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md";      DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE";        DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";                        Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";                  Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch the application right after installation.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
