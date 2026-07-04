# Instalación y Empaquetado — Video Converter

## Desarrollo

```bash
pip install -r requirements.txt
python main.py
```

FFmpeg debe estar en el `PATH` del sistema para ejecutar en modo desarrollo.

---

## Empaquetar (distribución)

El script `build.sh` lo hace todo: crea un virtualenv, descarga FFmpeg estático y compila un ejecutable single-file con PyInstaller.

```bash
./build.sh
```

Salida: `dist/VideoConverter` — binario único autocontenido (~200 MB).

### ¿Qué hace build.sh?

1. Crea `.venv/` con PyInstaller, PyQt5 y ffmpeg-python.
2. Descarga `ffmpeg` y `ffprobe` estáticos a `ffmpeg_bins/` desde johnvansickle.com (solo si no están presentes).
3. Genera `assets/icon.png` si no existe.
4. Ejecuta `pyinstaller VideoConverter.spec --clean`.

> `ffmpeg_bins/` está en `.gitignore` — se regenera automáticamente al compilar.

### Spec de PyInstaller

`VideoConverter.spec` en la raíz del proyecto. Embebe `ffmpeg_bins/ffmpeg` y `ffmpeg_bins/ffprobe` en el ejecutable bajo `bin/`. La ruta se resuelve en tiempo de ejecución desde `vconv/config.py` vía `sys._MEIPASS`.

### Prerequisitos del sistema para compilar

```bash
# Ubuntu/Debian
sudo apt install python3-venv curl

# El resto lo instala build.sh en el virtualenv
```

---

## Verificar el ejecutable

```bash
./dist/VideoConverter &
# o en modo terminal para ver logs:
./dist/VideoConverter 2>&1
```

```bash
# Verificar que FFmpeg está embebido
strings dist/VideoConverter | grep -c ffmpeg
```

---

## Instalar como paquete .deb (Ubuntu 24.04+)

Genera un `.deb` que instala la app en `/opt/videoconverter/` con acceso directo en el menú de aplicaciones.

### Generar el .deb

```bash
./build-deb.sh
```

Salida: `dist/videoconverter_1.0.0_amd64.deb`

> `build-deb.sh` ejecuta `build.sh` automáticamente si el binario no existe.

### Instalar

```bash
sudo dpkg -i dist/videoconverter_1.0.0_amd64.deb
# Si faltan dependencias:
sudo apt -f install
```

### Ejecutar

```bash
videoconverter
```

También aparece en el menú de aplicaciones como "VideoConverter".

### Desinstalar

```bash
sudo dpkg -r videoconverter
```

### Estructura instalada

```
/opt/videoconverter/
  VideoConverter          ← binario ejecutable
  assets/icon.png         ← icono de la app
/usr/bin/videoconverter   → symlink al binario
/usr/share/applications/videoconverter.desktop
/usr/share/icons/hicolor/256x256/apps/videoconverter.png
```
