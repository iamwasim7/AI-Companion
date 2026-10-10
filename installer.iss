; AI Companion — Inno Setup installer definition (Phase 11 follow-up).
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php), then run:
;   iscc installer.iss
; Output: dist-installer\AI-Companion-Setup-1.3.0.exe
; Build the app first: python -m PyInstaller ai-companion.spec --noconfirm
; NOT bundled: Tesseract OCR (install separately or set TESSERACT_PATH).

#define MyAppName "AI Companion"
#define MyAppVersion "1.3.0"
#define MyAppExeName "AI-Companion.exe"

[Setup]
AppId={{7E4A9B2C-1D5F-4A8E-9C3B-6F0A2D4E8B1A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\AI Companion
DefaultGroupName=AI Companion
OutputDir=dist-installer
OutputBaseFilename=AI-Companion-Setup-{#MyAppVersion}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
; App payload (one-dir PyInstaller build).
; Excludes keep the builder's private files OUT of the shipped installer:
; your .env (live API keys), your history database, and your logs.
Source: "dist\AI-Companion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env,data\*,logs\*"
; First-run .env template only — never overwrite the user's real keys.
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\AI Companion"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\AI Companion"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch AI Companion"; Flags: nowait postinstall skipifsilent
