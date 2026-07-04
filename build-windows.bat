@echo off
setlocal enabledelayedexpansion
REM Build script for VideoConverter (Windows, single-file bundle with FFmpeg)
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "FFMPEG_DIR=%SCRIPT_DIR%ffmpeg_bins"
set "ICON_PATH=%SCRIPT_DIR%assets\icon.png"
set "ICON_ICO=%SCRIPT_DIR%assets\icon.ico"
set "VENV=%SCRIPT_DIR%.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"

REM ── 1. Validar prerequisitos ────────────────────────────────────────────────
echo [build] Verificando prerequisitos...

where python >nul 2>&1
if errorlevel 1 (
    echo [build] Error: Python 3 no encontrado en PATH.
    echo         Descarga desde https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo [build] Python detectado: %PYVER%

where pip >nul 2>&1
if errorlevel 1 (
    echo [build] Error: pip no encontrado.
    echo         Ejecuta: python -m ensurepip --upgrade
    exit /b 1
)

REM ── 2. Entorno virtual ──────────────────────────────────────────────────────
if not exist "%PY%" (
    echo [build] Creando entorno virtual...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [build] Error al crear entorno virtual.
        exit /b 1
    )
)

echo [build] Instalando dependencias en el venv...
"%PIP%" install -q pyinstaller PyQt5 ffmpeg-python Pillow
if errorlevel 1 (
    echo [build] Error al instalar dependencias.
    exit /b 1
)

REM ── 3. FFmpeg estático ─────────────────────────────────────────────────────
if not exist "%FFMPEG_DIR%\ffmpeg.exe" (
    echo [build] Descargando FFmpeg para Windows desde gyan.dev...
    if not exist "%FFMPEG_DIR%" mkdir "%FFMPEG_DIR%"

    set "FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    set "TMPDIR_BUILD=%TEMP%\ffmpeg_build_%RANDOM%"
    mkdir "!TMPDIR_BUILD!"

    echo [build] Descargando...
    curl -L --progress-bar "!FFMPEG_URL!" -o "!TMPDIR_BUILD!\ffmpeg.zip"
    if errorlevel 1 (
        echo [build] Error al descargar FFmpeg.
        echo         Descarga manualmente desde: !FFMPEG_URL%
        echo         Extrae ffmpeg.exe y ffprobe.exe a: %FFMPEG_DIR%
        rmdir /s /q "!TMPDIR_BUILD!"
        exit /b 1
    )

    echo [build] Extrayendo...
    powershell -Command "Expand-Archive -Path '!TMPDIR_BUILD!\ffmpeg.zip' -DestinationPath '!TMPDIR_BUILD!\extracted' -Force"

    REM Buscar ffmpeg.exe y ffprobe.exe en los archivos extraidos
    for /r "!TMPDIR_BUILD!\extracted" %%f in (ffmpeg.exe) do (
        copy "%%f" "%FFMPEG_DIR%\ffmpeg.exe" >nul
    )
    for /r "!TMPDIR_BUILD!\extracted" %%f in (ffprobe.exe) do (
        copy "%%f" "%FFMPEG_DIR%\ffprobe.exe" >nul
    )

    rmdir /s /q "!TMPDIR_BUILD!"

    if not exist "%FFMPEG_DIR%\ffmpeg.exe" (
        echo [build] Error: No se encontro ffmpeg.exe despues de la extraccion.
        exit /b 1
    )
    echo [build] FFmpeg descargado: %FFMPEG_DIR%
) else (
    echo [build] FFmpeg ya presente en %FFMPEG_DIR%
)

REM ── 4. Icono ICO ────────────────────────────────────────────────────────────
if not exist "%ICON_ICO%" (
    echo [build] Generando icono ICO...
    if not exist "%SCRIPT_DIR%assets" mkdir "%SCRIPT_DIR%assets"
    "%PY%" - "%ICON_PATH%" "%ICON_ICO%" <<'PYTHON'
import sys
from PIL import Image

src = sys.argv[1]
dst = sys.argv[2]
img = Image.open(src)
sizes = [(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]
img.save(dst, format="ICO", sizes=sizes)
print(f"  Icono ICO guardado en {dst}")
PYTHON
    if errorlevel 1 (
        echo [build] Advertencia: No se pudo generar icono ICO. PyInstaller usara el PNG.
    )
)

REM ── 5. Compilar ─────────────────────────────────────────────────────────────
echo [build] Compilando con PyInstaller...
"%PY%" -m PyInstaller "%SCRIPT_DIR%VideoConverter.spec" --clean --noconfirm
if errorlevel 1 (
    echo [build] Error al compilar con PyInstaller.
    exit /b 1
)

echo.
echo Listo. Binario en: %SCRIPT_DIR%dist\VideoConverter.exe
