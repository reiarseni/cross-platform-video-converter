#!/usr/bin/env bash
# Build script for VideoConverter (Linux, single-file bundle with FFmpeg)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FFMPEG_DIR="$SCRIPT_DIR/ffmpeg_bins"
ICON_PATH="$SCRIPT_DIR/assets/icon.png"
VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

# ── 1. Entorno virtual ────────────────────────────────────────────────────────
if [ ! -f "$PY" ]; then
    echo "[build] Creando entorno virtual..."
    python3 -m venv "$VENV"
fi

echo "[build] Instalando dependencias en el venv..."
"$PIP" install -q pyinstaller PyQt5 ffmpeg-python Pillow

# ── 2. FFmpeg static binaries ─────────────────────────────────────────────────
if [ ! -f "$FFMPEG_DIR/ffmpeg" ] || [ ! -f "$FFMPEG_DIR/ffprobe" ]; then
    echo "[build] Descargando FFmpeg estático para Linux (amd64)..."
    mkdir -p "$FFMPEG_DIR"
    TMPDIR_BUILD=$(mktemp -d)
    FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    curl -L --progress-bar "$FFMPEG_URL" -o "$TMPDIR_BUILD/ffmpeg.tar.xz"
    tar -xf "$TMPDIR_BUILD/ffmpeg.tar.xz" -C "$TMPDIR_BUILD"
    cp "$(find "$TMPDIR_BUILD" -name "ffmpeg"  -type f | head -1)" "$FFMPEG_DIR/ffmpeg"
    cp "$(find "$TMPDIR_BUILD" -name "ffprobe" -type f | head -1)" "$FFMPEG_DIR/ffprobe"
    chmod +x "$FFMPEG_DIR/ffmpeg" "$FFMPEG_DIR/ffprobe"
    rm -rf "$TMPDIR_BUILD"
    echo "[build] FFmpeg descargado: $FFMPEG_DIR"
else
    echo "[build] FFmpeg ya presente en $FFMPEG_DIR"
fi

# ── 3. Icono ──────────────────────────────────────────────────────────────────
if [ ! -f "$ICON_PATH" ]; then
    echo "[build] Generando icono..."
    mkdir -p "$SCRIPT_DIR/assets"
    "$PY" - "$ICON_PATH" <<'PYTHON'
import sys
from PIL import Image, ImageDraw
size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.ellipse([4, 4, size-4, size-4], fill=(25, 28, 60), outline=(80, 130, 230), width=8)
draw.polygon([(82, 72), (82, 184), (190, 128)], fill=(255, 255, 255))
img.save(sys.argv[1])
print(f"  Icono guardado en {sys.argv[1]}")
PYTHON
fi

# ── 4. Compilar ───────────────────────────────────────────────────────────────
echo "[build] Compilando con PyInstaller..."
"$PY" -m PyInstaller "$SCRIPT_DIR/VideoConverter.spec" --clean --noconfirm

echo ""
echo "Listo. Binario en: $SCRIPT_DIR/dist/VideoConverter"
echo "Tamano: $(du -sh "$SCRIPT_DIR/dist/VideoConverter" 2>/dev/null | cut -f1)"
