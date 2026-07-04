; VideoConverter NSIS Installer Script
; Requires: NSIS 3.x (https://nsis.sourceforge.io/Download)

!include "MUI2.nsh"

; ── Configuración ────────────────────────────────────────────────────────────
!define APP_NAME "VideoConverter"
!define APP_VERSION "1.0.0"
!define APP_PUBLISHER "VideoConverter Team"
!define APP_EXE "VideoConverter.exe"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "dist\${APP_NAME}-Setup-${APP_VERSION}.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "${UNINSTALL_KEY}" "InstallLocation"
RequestExecutionLevel admin

; ── Iconos ───────────────────────────────────────────────────────────────────
!define MUI_ICON "assets\icon.ico"
!define MUI_UNICON "assets\icon.ico"
!define MUI_ABORTWARNING

; ── Páginas del asistente ────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"

; ── Sección de instalación ───────────────────────────────────────────────────
Section "Install"
    SetOutPath "${INSTALL_DIR}"

    ; Archivos principales
    File "dist\${APP_EXE}"
    File /r "ffmpeg_bins\*.*"

    ; Icono
    CreateDirectory "${INSTALL_DIR}\assets"
    File "assets\icon.ico"

    ; Acceso directo en escritorio
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "${INSTALL_DIR}\${APP_EXE}" "" "${INSTALL_DIR}\assets\icon.ico"

    ; Entrada en Menú Inicio
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "${INSTALL_DIR}\${APP_EXE}" "" "${INSTALL_DIR}\assets\icon.ico"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Desinstalar ${APP_NAME}.lnk" "${INSTALL_DIR}\uninstall.exe"

    ; Desinstalador
    WriteUninstaller "${INSTALL_DIR}\uninstall.exe"

    ; Registro de desinstalación
    WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" '"${INSTALL_DIR}\uninstall.exe"'
    WriteRegStr HKLM "${UNINSTALL_KEY}" "InstallLocation" "${INSTALL_DIR}"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

; ── Sección de desinstalación ────────────────────────────────────────────────
Section "Uninstall"
    ; Eliminar archivos
    Delete "${INSTALL_DIR}\${APP_EXE}"
    Delete "${INSTALL_DIR}\uninstall.exe"
    Delete "${INSTALL_DIR}\assets\icon.ico"
    RMDir /r "${INSTALL_DIR}\assets"
    RMDir /r "${INSTALL_DIR}\ffmpeg_bins"
    RMDir "${INSTALL_DIR}"

    ; Eliminar accesos directos
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Desinstalar ${APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"

    ; Eliminar registro
    DeleteRegKey HKLM "${UNINSTALL_KEY}"
SectionEnd
