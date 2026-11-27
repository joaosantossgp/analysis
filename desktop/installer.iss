; Per-user Setup.exe for CVM Analytics (Inno Setup 6; issue #632, ADR 0011).
; Packs the same dist\CVMAnalytics bundle as the publication ZIP:
;
;   ISCC.exe /DAppVersion=<version> desktop\installer.iss
;
; The installed app updates itself in place: desktop/updater.py and
; update_helper.ps1 swap CVMAnalytics.exe and _internal in this folder, which
; is user-writable. User data (%USERPROFILE%\Documents\CVMAnalytics) and updater
; state (%LOCALAPPDATA%\CVMAnalytics) are never installed or removed here.
; Contract: docs/build-release.md, "Installer".

#ifndef AppVersion
  #error Pass the publication version: ISCC.exe /DAppVersion=<version> desktop\installer.iss
#endif

[Setup]
; Fixed AppId: a newer Setup.exe installs over the existing install.
AppId={{444CE8B1-A186-43DF-9B0D-4BE59C85D541}
AppName=CVM Analytics
AppVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\CVMAnalytics
DisableDirPage=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\CVMAnalytics.exe
OutputDir=..\dist
OutputBaseFilename=CVMAnalytics-Setup-v{#AppVersion}
; CloseApplications keeps its default (yes): a running app is detected and the
; user is asked to close it before files are replaced.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Same as update_helper.ps1: replace _internal whole so no stale files remain.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\CVMAnalytics\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CVM Analytics"; Filename: "{app}\CVMAnalytics.exe"
Name: "{autodesktop}\CVM Analytics"; Filename: "{app}\CVMAnalytics.exe"; Tasks: desktopicon

[UninstallDelete]
; In-app updates replace these two bundle entries with files this uninstaller
; did not log. Only bundle entries are listed; {app} itself is removed only
; when it is empty.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\CVMAnalytics.exe"
