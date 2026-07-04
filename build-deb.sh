#!/usr/bin/env bash
# Build script for VideoConverter .deb package (Ubuntu 24.04+, amd64)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="1.0.0"
PKG_NAME="videoconverter"
ARCH="amd64"
DEB_NAME="${PKG_NAME}_${VERSION}_${ARCH}.deb"

BUILD_DIR="$SCRIPT_DIR/build/deb"
DIST_DIR="$SCRIPT_DIR/dist"

# ── 1. Validación del sistema ────────────────────────────────────────────────
if ! command -v dpkg-deb &>/dev/null; then
    echo "[build-deb] Error: dpkg-deb no encontrado. Instalar dpkg."
    exit 1
fi

UBUNTU_VERSION=$(lsb_release -rs 2>/dev/null || echo "0")
if [ "$(echo "$UBUNTU_VERSION >= 24.04" | bc -l 2>/dev/null || echo 0)" != "1" ]; then
    echo "[build-deb] Advertencia: Ubuntu $UBUNTU_VERSION detectado. El .deb está optimizado para 24.04+."
fi

# ── 2. Generar binario PyInstaller ───────────────────────────────────────────
echo "[build-deb] Ejecutando build.sh para generar binario actualizado..."
bash "$SCRIPT_DIR/build.sh"

if [ ! -f "$DIST_DIR/VideoConverter" ]; then
    echo "[build-deb] Error: build.sh no generó el binario."
    exit 1
fi

# ── 3. Crear estructura temporal del .deb ────────────────────────────────────
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/opt/videoconverter/assets"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"

# ── 4. Archivo DEBIAN/control ────────────────────────────────────────────────
cat > "$BUILD_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: libc6, libgl1-mesa-glx | libgl1, libxkbcommon0
Maintainer: VideoConverter Team <noreply@videoconverter.local>
Description: Conversor de Video por lotes
 Aplicación de escritorio para conversión de video por lotes
 usando FFmpeg. Soporta múltiples formatos, presets de calidad,
 aceleración por hardware (NVENC, QSV, AMF), y arrastrar-soltar.
EOF

# ── 5. Copiar archivos al paquete ────────────────────────────────────────────
echo "[build-deb] Copiando binario..."
cp "$DIST_DIR/VideoConverter" "$BUILD_DIR/opt/videoconverter/VideoConverter"
chmod 755 "$BUILD_DIR/opt/videoconverter/VideoConverter"

echo "[build-deb] Copiando icono..."
cp "$SCRIPT_DIR/assets/icon.png" "$BUILD_DIR/opt/videoconverter/assets/icon.png"
cp "$SCRIPT_DIR/assets/icon.png" "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/videoconverter.png"

# ── 6. Symlink en /usr/bin ──────────────────────────────────────────────────
ln -sf /opt/videoconverter/VideoConverter "$BUILD_DIR/usr/bin/videoconverter"

# ── 7. Archivo .desktop ─────────────────────────────────────────────────────
cat > "$BUILD_DIR/usr/share/applications/videoconverter.desktop" <<EOF
[Desktop Entry]
Name=VideoConverter
GenericName=Video Converter
Comment=Conversor de video por lotes
Exec=/usr/bin/videoconverter
Icon=videoconverter
Terminal=false
Type=Application
Categories=AudioVideo;Video;
MimeType=video/mp4;video/x-msvideo;video/quicktime;video/x-matroska;
StartupNotify=true
EOF

# ── 8. Generar el .deb ──────────────────────────────────────────────────────
echo "[build-deb] Generando $DEB_NAME..."
dpkg-deb --build "$BUILD_DIR" "$DIST_DIR/$DEB_NAME"

echo ""
echo "Listo. Paquete en: $DIST_DIR/$DEB_NAME"
echo "Tamano: $(du -sh "$DIST_DIR/$DEB_NAME" 2>/dev/null | cut -f1)"
echo ""
echo "Para instalar: sudo dpkg -i dist/$DEB_NAME"
echo "Para ejecutar: videoconverter"
echo "Para desinstalar: sudo dpkg -r $PKG_NAME"
