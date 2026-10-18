; ---------------------------------------------------------------------------
; ZARAZ setup script (NSIS 3)
;
; Installs ZARAZ for all users into C:\Program Files, asks for permission with
; a mandatory checkbox, optionally creates a desktop shortcut and optionally
; writes the uninstall files (uninstaller + Windows "Apps & Features" entry).
;
; Build:  python installer/build_installer.py   (or: makensis zaraz.nsi)
; ---------------------------------------------------------------------------

Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "nsDialogs.nsh"

!define APP_NAME "ZARAZ"
!define APP_TAGLINE "Your saves, instantly there."
!define APP_PUBLISHER "Jonas Raphael"
!define APP_ID "ZARAZ"
!define UNINSTALLER_NAME "Uninstall ZARAZ.exe"
!define REG_APP "Software\ZARAZ"
!define REG_UNINSTALL "Software\Microsoft\Windows\CurrentVersion\Uninstall\ZARAZ"

!ifndef APP_VERSION
  !define APP_VERSION "0.1.0"
!endif
!ifndef PAYLOAD_DIR
  !define PAYLOAD_DIR "payload"
!endif

Name "${APP_NAME} ${APP_VERSION}"
Caption "${APP_NAME} ${APP_VERSION} Setup"
OutFile "..\releases\Zaraz-Setup-${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${REG_APP}" "InstallDir"
RequestExecutionLevel admin

; --- Interface --------------------------------------------------------------
!define MUI_ABORTWARNING
!define MUI_ICON "zaraz.ico"
!define MUI_UNICON "zaraz.ico"
!define MUI_WELCOMEPAGE_TITLE "Install ${APP_NAME} ${APP_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "This wizard installs ${APP_NAME} for all users into C:\Program Files and lets you choose shortcuts and uninstall files.$\r$\n$\r$\n${APP_NAME} backs up save files from SD cards to your PC.$\r$\n$\r$\n${APP_NAME} is not affiliated with or endorsed by Nintendo."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
Page custom OptionsPage OptionsPageLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN ""
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchZaraz"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; --- Runtime variables ------------------------------------------------------
Var OptionsDialog
Var ConsentCheck
Var DesktopCheck
Var UninstallCheck
Var CreateDesktop
Var CreateUninstaller

Function .onInit
  SetRegView 64
FunctionEnd

Function un.onInit
  SetRegView 64
FunctionEnd

Function LaunchZaraz
  Exec '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\app\Zaraz.pyw"'
FunctionEnd

; --- Installation options page ---------------------------------------------
Function OptionsPage
  !insertmacro MUI_HEADER_TEXT "Installation options" "Confirm the installation and choose the shortcuts."

  nsDialogs::Create 1018
  Pop $OptionsDialog
  ${If} $OptionsDialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 26u "${APP_NAME} is installed for all users into C:\Program Files. Windows will ask for administrator permission. Please only continue if you are allowed to install software on this computer."
  Pop $0

  ${NSD_CreateCheckbox} 0 36u 100% 12u "I have permission to install ${APP_NAME} on this computer."
  Pop $ConsentCheck
  ${NSD_Check} $ConsentCheck

  ${NSD_CreateCheckbox} 0 58u 100% 12u "Create a desktop shortcut"
  Pop $DesktopCheck
  ${NSD_Check} $DesktopCheck

  ${NSD_CreateCheckbox} 0 80u 100% 12u "Create uninstall files (recommended)"
  Pop $UninstallCheck
  ${NSD_Check} $UninstallCheck

  ${NSD_CreateLabel} 13u 94u 87% 22u "Adds an entry in Windows Settings and an Uninstall button inside ${APP_NAME}, so the app can be removed with one click at any time."
  Pop $0

  nsDialogs::Show
FunctionEnd

Function OptionsPageLeave
  ${NSD_GetState} $ConsentCheck $0
  ${If} $0 != ${BST_CHECKED}
    MessageBox MB_ICONEXCLAMATION|MB_OK "Please confirm that you have permission to install ${APP_NAME} before continuing."
    Abort
  ${EndIf}

  StrCpy $CreateDesktop "0"
  StrCpy $CreateUninstaller "0"

  ${NSD_GetState} $DesktopCheck $1
  ${If} $1 == ${BST_CHECKED}
    StrCpy $CreateDesktop "1"
  ${EndIf}

  ${NSD_GetState} $UninstallCheck $2
  ${If} $2 == ${BST_CHECKED}
    StrCpy $CreateUninstaller "1"
  ${EndIf}
FunctionEnd

; --- Install ----------------------------------------------------------------
Section "ZARAZ (required)" SecMain
  SectionIn RO
  SetRegView 64
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File /r "${PAYLOAD_DIR}\*.*"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
    "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\app\Zaraz.pyw"' \
    "$INSTDIR\Zaraz.ico" 0 SW_SHOWNORMAL "" "${APP_NAME} – ${APP_TAGLINE}"

  ${If} $CreateDesktop == "1"
    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" \
      "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\app\Zaraz.pyw"' \
      "$INSTDIR\Zaraz.ico" 0 SW_SHOWNORMAL "" "${APP_NAME} – ${APP_TAGLINE}"
  ${Else}
    Delete "$DESKTOP\${APP_NAME}.lnk"
  ${EndIf}

  WriteRegStr HKLM "${REG_APP}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${REG_APP}" "Version" "${APP_VERSION}"

  ${If} $CreateUninstaller == "1"
    WriteUninstaller "$INSTDIR\${UNINSTALLER_NAME}"
    WriteRegStr HKLM "${REG_APP}" "Uninstaller" "$INSTDIR\${UNINSTALLER_NAME}"
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" \
      "$INSTDIR\${UNINSTALLER_NAME}"

    WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "${REG_UNINSTALL}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayIcon" "$INSTDIR\Zaraz.ico"
    WriteRegStr HKLM "${REG_UNINSTALL}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${REG_UNINSTALL}" "UninstallString" '"$INSTDIR\${UNINSTALLER_NAME}"'
    WriteRegStr HKLM "${REG_UNINSTALL}" "QuietUninstallString" '"$INSTDIR\${UNINSTALLER_NAME}" /S'
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoModify" 1
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoRepair" 1
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "EstimatedSize" $0
  ${EndIf}
SectionEnd

; --- Uninstall --------------------------------------------------------------
Section "Uninstall"
  SetRegView 64
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  DeleteRegKey HKLM "${REG_UNINSTALL}"
  DeleteRegKey HKLM "${REG_APP}"
  RMDir /r "$INSTDIR"
SectionEnd
