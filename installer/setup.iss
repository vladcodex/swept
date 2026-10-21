; ============================================================================
;  Swept — установщик (Inno Setup 6)
;
;  Что делает: ставит Swept в «Program Files», создаёт ярлыки в меню «Пуск»
;  и (по желанию) на рабочем столе, прописывается в «Установка и удаление
;  программ» и получает полноценный деинсталлятор.
;
;  Как собрать:
;    1. Поставить Inno Setup 6 (один раз):
;         winget install JRSoftware.InnoSetup
;    2. Скомпилировать скрипт (из корня проекта):
;         "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
;       или открыть installer\setup.iss в Inno Setup и нажать Build → Compile.
;
;  Результат: dist\Swept-Setup-1.1.0.exe
;
;  Важно: перед сборкой должен существовать dist\Swept.exe
;  (python build.py), иначе компиляция упадёт на шаге [Files].
; ============================================================================

#define MyAppName "Swept"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "vladcodex"
#define MyAppURL "https://github.com/vladcodex/swept"
#define MyAppExeName "Swept.exe"
; Идентификатор приложения: любая уникальная строка-GUID. Менять нельзя после
; первого выпуска — иначе Windows посчитает установщик другой программой.
#define MyAppId "{7E2A9F31-4C6B-4D8E-A1F2-3B5C9D0E7A64}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
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
; Программа 64-битная.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Swept чистит системный кэш и обновляет политики, поэтому ему нужны права
; администратора — их же запрашивает и манифест самого .exe.
PrivilegesRequired=admin
MinVersion=10.0

[Languages]
; Установщик говорит на тех же двух языках, что и программа.
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Ярлык на рабочем столе — не по умолчанию, а по желанию.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Swept.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";      DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE";        DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";                        Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";                  Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Предложить запустить программу сразу после установки.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
