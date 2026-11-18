#define AppName "PDF Studio Pro"
#define AppVersion "1.0.0"
#define AppPublisher "PDF Studio Pro"
#define SourceDir "..\dist\PDF-Studio-Pro"

[Setup]
AppId={{1C18069C-C48F-4AF7-B3BD-C18D077B8116}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\PDF Studio Pro
DefaultGroupName=PDF Studio Pro
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=PDF-Studio-Pro-Setup-1.0.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\PDF-Studio-Pro.exe
SetupIconFile=..\assets\pdfstudio.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PDF Studio Pro"; Filename: "{app}\PDF-Studio-Pro.exe"
Name: "{autodesktop}\PDF Studio Pro"; Filename: "{app}\PDF-Studio-Pro.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\PDF-Studio-Pro.exe"; Description: "Launch PDF Studio Pro"; Flags: nowait postinstall skipifsilent
