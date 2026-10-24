; Inno Setup script for the eyeokuri installer. build-windows.bat compiles it after PyInstaller
; fills build\dist\eyeokuri, passing the version as /DAppVersion=...

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Keep AppId unchanged: Windows uses it to recognize upgrades and the uninstaller.
AppId={{100F70DC-B0E9-4B78-B51C-1AA890BCDFFF}
AppName=eyeokuri
AppVersion={#AppVersion}
AppPublisher=lulalala
AppPublisherURL=https://lulalala.github.io/eyeokuri/
AppSupportURL=https://github.com/lulalala/eyeokuri/issues
; Per-user install into %LOCALAPPDATA%\Programs, so no admin prompt.
PrivilegesRequired=lowest
DefaultDirName={autopf}\eyeokuri
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=build
OutputBaseFilename=eyeokuri-setup
SetupIconFile=build\eyeokuri.ico
UninstallDisplayIcon={app}\eyeokuri.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
; config.toml is saved in the working directory; keeping it here means upgrades and uninstalls leave it alone.
Name: "{userappdata}\eyeokuri"

[InstallDelete]
; Remove libraries from the previous version before copying the new ones.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "build\dist\eyeokuri\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\eyeokuri"; Filename: "{app}\eyeokuri.exe"; WorkingDir: "{userappdata}\eyeokuri"
Name: "{autodesktop}\eyeokuri"; Filename: "{app}\eyeokuri.exe"; WorkingDir: "{userappdata}\eyeokuri"; Tasks: desktopicon

[Run]
Filename: "{app}\eyeokuri.exe"; WorkingDir: "{userappdata}\eyeokuri"; Description: "{cm:LaunchProgram,eyeokuri}"; Flags: nowait postinstall skipifsilent
