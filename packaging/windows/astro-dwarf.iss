#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{BD479E1A-0DC2-4D26-AF58-58DE279A651F}
AppName=Astro Dwarf
AppVersion={#AppVersion}
AppPublisher=Astro Dwarf
DefaultDirName={autopf}\Astro Dwarf
DefaultGroupName=Astro Dwarf
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=AstroDwarf-Setup-{#AppVersion}-win64
SetupIconFile=..\icons\astro-dwarf.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\AstroDwarf.exe

[Files]
Source: "..\..\dist\AstroDwarf\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Astro Dwarf"; Filename: "{app}\AstroDwarf.exe"
Name: "{autodesktop}\Astro Dwarf"; Filename: "{app}\AstroDwarf.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\AstroDwarf.exe"; Description: "Launch Astro Dwarf"; Flags: nowait postinstall skipifsilent
