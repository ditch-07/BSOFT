; NRZ Student Management - Inno Setup Script
; Build: iscc NRZ_Student_Management.iss

#define AppName "NRZ Student Management"
#define AppVersion "1.0.0"
#define AppPublisher "NRZ"
#define AppExeName "NRZ Student Management.exe"
#define SourceDir "dist\NRZ Student Management"
#define DataDir "{commonappdata}\{#AppName}"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={pf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=NRZ_Student_Management_Setup_{#AppVersion}
SetupIconFile={#SourceDir}\NRZ Student Management.exe
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
DisableDirPage=no
DisableProgramGroupPage=no
CreateAppDir=yes
AllowNoIcons=yes
AppCopyright=Copyright © 2026 NRZ
AppModifyPath={pf}\{#AppName}\unins000.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1

[Files]
; Main executable and all dependencies
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Create writable data directory in ProgramData
; This is where the SQLite database and backups will live
Source: "data\*"; DestDir: "{#DataDir}"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist
Source: "backups\*"; DestDir: "{#DataDir}\backups"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: quicklaunchicon

[Registry]
; Set NRZ_DATA_DIR environment variable for the application
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "NRZ_DATA_DIR"; ValueData: "{#DataDir}"; Flags: preservestringtype

[Run]
; Optionally launch the application after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove the writable data directory on uninstall (optional - keep user data)
; Type: filesandordirs; Name: "{#DataDir}"

[UninstallRegistry]
; Remove the environment variable on uninstall
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueName: "NRZ_DATA_DIR"; ValueType: expandsz

[Code]
; Custom function to set up data directory permissions if needed
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

; Ensure data directory exists with correct permissions
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: string;
begin
  if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{#DataDir}');
    if not DirExists(DataDir) then
      ForceDirectories(DataDir);
    
    DataDir := DataDir + '\backups';
    if not DirExists(DataDir) then
      ForceDirectories(DataDir);
  end;
end;