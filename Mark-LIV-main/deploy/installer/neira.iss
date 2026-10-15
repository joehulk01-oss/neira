; ============================================================================
;  Neira — installer Windows (Inno Setup 6)
;  Prasyarat : deploy\build_exe.bat sudah dijalankan (ada dist\Neira\)
;  Build     : buka file ini di Inno Setup Compiler → Compile (F9)
;  Hasil     : Output\Neira-Setup-1.0.0.exe
;
;  Setelah install, mode remote diatur di: {app}\shared\config.env
;    GATEWAY_URL=        (kosong = mode LAN lama)
;    GATEWAY_TOKEN=      (kredensial PC ke Neira Gateway di VPS)
; ============================================================================

#define AppName "Neira"
#define AppVersion "1.0.0"
#define AppPublisher "Neira Project"
#define AppExeName "Neira.exe"

[Setup]
AppId={{5E1F6A64-9C0B-4C7D-9C4A-2B7D91A00001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=Neira-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\Neira\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
