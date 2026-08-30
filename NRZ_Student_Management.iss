; NRZ Student Management - Inno Setup Script
; Build: iscc NRZ_Student_Management.iss

#define AppName "NRZ Student Management"
#define AppVersion "1.0.0"
#define AppPublisher "NRZ"
#define AppExeName "NRZ Student Management.exe"
#define SourceDir "dist\NRZ Student Management"
#define DataDir "{commonappdata}\NRZ Student Management"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={pf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=NRZ_Student_Management_Setup_{#AppVersion}
; SetupIconFile={#SourceDir}\NRZ Student Management.exe
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
; Enable detailed logging - use SetupLogging directive
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1

[Files]
; Main executable and all dependencies
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Note: data/ and backups/ are NOT included - they will be created fresh in ProgramData
; The SQLite database will be created automatically by Django on first run

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
var
  InstallLogPath: string;

function InitializeSetup(): Boolean;
var
  SourcePath: string;
begin
  Result := True;
  
  // Verify source directory exists
  SourcePath := ExpandConstant('{#SourceDir}');
  if not DirExists(SourcePath) then
  begin
    MsgBox('ERROR: Source directory not found: ' + SourcePath + #13#10 + 
           'Please run the build script first to create the dist folder.', 
           mbCriticalError, MB_OK);
    Result := False;
  end;
  
  // Verify main executable exists
  if not FileExists(SourcePath + '\NRZ Student Management.exe') then
  begin
    MsgBox('ERROR: Main executable not found: ' + SourcePath + '\NRZ Student Management.exe' + #13#10 +
           'Please run: pyinstaller nrz_student_management.spec --noconfirm', 
           mbCriticalError, MB_OK);
    Result := False;
  end;
end;

function ShouldSkipFile(SourceName, DestName: string; var Skip: Boolean): Boolean;
begin
  Result := False;
  Skip := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: string;
  ErrCode: Integer;
begin
  if CurStep = ssInstall then
  begin
  end
  else if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{#DataDir}');
    if not DirExists(DataDir) then
    begin
      ForceDirectories(DataDir);
    end;
    
    DataDir := DataDir + '\backups';
    if not DirExists(DataDir) then
    begin
      ForceDirectories(DataDir);
    end;
    
    // Set permissions on data directory for all users
    try
      Exec('icacls.exe', ExpandConstant('{#DataDir}') + ' /grant "Users:(OI)(CI)F" /T', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
    except
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
end;

begin
end.