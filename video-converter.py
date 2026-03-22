import os
import sys
import subprocess
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton, QComboBox, QProgressBar,
                             QLabel, QFileDialog, QMessageBox, QSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
import ffmpeg

# Encoder labels
ENCODER_AUTO   = "Auto"
ENCODER_CPU    = "CPU"
ENCODER_NVIDIA = "NVIDIA (NVENC)"
ENCODER_INTEL  = "Intel (QSV)"
ENCODER_AMD    = "AMD (AMF)"

def _scan_ffmpeg_encoder_list():
    """Queries ffmpeg -encoders and returns the raw text output."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout + result.stderr
    except Exception:
        return ""

def _has_encoder(codec, encoder_text):
    """Returns True if codec name appears in the ffmpeg -encoders output."""
    return codec in encoder_text

_FFMPEG_ENCODERS_TEXT = _scan_ffmpeg_encoder_list()

# Build list of available encoders at startup (Auto and CPU are always available)
AVAILABLE_ENCODERS = [ENCODER_AUTO, ENCODER_CPU]
_GPU_CANDIDATES = [
    (ENCODER_NVIDIA, ['h264_nvenc', 'hevc_nvenc']),
    (ENCODER_INTEL,  ['h264_qsv',   'hevc_qsv']),
    (ENCODER_AMD,    ['h264_amf',   'hevc_amf']),
]
for _label, _codecs in _GPU_CANDIDATES:
    if any(_has_encoder(c, _FFMPEG_ENCODERS_TEXT) for c in _codecs):
        AVAILABLE_ENCODERS.append(_label)

# Supported video file extensions
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp']

def is_video_file(file_path):
    """Checks if a file is a video based on its extension"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_EXTENSIONS

def get_video_codec(file_path):
    """Detects the video codec of the given file using ffmpeg.probe"""
    try:
        probe = ffmpeg.probe(file_path)
        video_streams = [stream for stream in probe['streams'] if stream.get('codec_type') == 'video']
        if video_streams:
            return video_streams[0].get('codec_name', 'Unknown')
        else:
            return "Unknown"
    except Exception:
        return "Unknown"

def get_video_duration(file_path):
    """Retrieves the duration of the video file in seconds using ffmpeg.probe"""
    try:
        probe = ffmpeg.probe(file_path)
        format_info = probe.get('format', {})
        duration = float(format_info.get('duration', 0))
        return duration
    except Exception:
        return 0

def format_duration(seconds):
    """Formats duration in seconds to HH:MM:SS format"""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def format_size(bytes_size):
    """Formats file size in bytes to a human-readable string"""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size/1024:.2f} KB"
    else:
        return f"{bytes_size/(1024*1024):.2f} MB"

class ConversionPreset:
    """
    Centralizes conversion parameters based on format preset and dependent quality selection.
    Follows the Single Responsibility Principle (SRP) for conversion parameter logic.
    """
    _preset_data = {
        "MP4 (H.264)": {
            "preset_quality": {"Baja": "28", "Media": "23", "Alta": "18"},
            "container": ".mp4",
            "vcodec": "libx264"
        },
        "MP4 (H.265)": {
            "preset_quality": {"Baja": "30", "Media": "25", "Alta": "20"},
            "container": ".mp4",
            "vcodec": "libx265"
        },
        "AVI (MPEG-4)": {
            "preset_quality": {"Baja": "32", "Media": "27", "Alta": "22"},
            "container": ".avi",
            "vcodec": "mpeg4"
        },
        "MKV (H.264)": {
            "preset_quality": {"Baja": "28", "Media": "23", "Alta": "18"},
            "container": ".mkv",
            "vcodec": "libx264"
        }
    }

    # GPU codec equivalents per format preset (AVI/mpeg4 has no GPU encoder in FFmpeg)
    _gpu_codec_map = {
        "MP4 (H.264)": {ENCODER_NVIDIA: "h264_nvenc", ENCODER_INTEL: "h264_qsv", ENCODER_AMD: "h264_amf"},
        "MP4 (H.265)": {ENCODER_NVIDIA: "hevc_nvenc", ENCODER_INTEL: "hevc_qsv", ENCODER_AMD: "hevc_amf"},
        "AVI (MPEG-4)": {},
        "MKV (H.264)": {ENCODER_NVIDIA: "h264_nvenc", ENCODER_INTEL: "h264_qsv", ENCODER_AMD: "h264_amf"},
    }

    def __init__(self, format_preset: str, quality: str):
        self.format_preset = format_preset
        self.quality = quality

    @classmethod
    def get_available_presets(cls):
        """Returns a list of available format presets."""
        return list(cls._preset_data.keys())

    @classmethod
    def get_available_qualities(cls):
        """Returns a list of available quality options."""
        if "MP4 (H.264)" in cls._preset_data:
            return list(cls._preset_data["MP4 (H.264)"]["preset_quality"].keys())
        else:
            first_key = next(iter(cls._preset_data))
            return list(cls._preset_data[first_key]["preset_quality"].keys())

    def get_crf(self) -> str:
        """Returns the CRF value based on the selected format preset and quality."""
        return self._preset_data.get(self.format_preset, {}) \
                   .get("preset_quality", {}) \
                   .get(self.quality, "23")

    def get_container_extension(self) -> str:
        """Returns the container extension based on the selected format preset."""
        return self._preset_data.get(self.format_preset, {}).get("container", ".mp4")

    def get_video_codec(self) -> str:
        """Returns the CPU video codec based on the selected format preset."""
        return self._preset_data.get(self.format_preset, {}).get("vcodec", "libx264")

    @classmethod
    def get_gpu_codec(cls, format_preset, encoder):
        """Returns the GPU codec name for the given preset and encoder, or None if unsupported."""
        return cls._gpu_codec_map.get(format_preset, {}).get(encoder)

    def resolve_encoder(self, preferred_encoder):
        """
        Returns (resolved_encoder_label, codec) for the given preference.
        Falls back to CPU if the GPU encoder is unavailable for this preset.
        """
        if preferred_encoder == ENCODER_CPU:
            return ENCODER_CPU, self.get_video_codec()

        if preferred_encoder == ENCODER_AUTO:
            for label in [ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD]:
                if label in AVAILABLE_ENCODERS:
                    gpu_codec = self.get_gpu_codec(self.format_preset, label)
                    if gpu_codec:
                        return label, gpu_codec
            return ENCODER_CPU, self.get_video_codec()

        # Specific GPU encoder requested
        gpu_codec = self.get_gpu_codec(self.format_preset, preferred_encoder)
        if gpu_codec:
            return preferred_encoder, gpu_codec
        # Preset doesn't support this GPU (e.g. AVI + NVENC) → fall back to CPU
        return ENCODER_CPU, self.get_video_codec()

class DragDropTableWidget(QTableWidget):
    """Custom TableWidget for dragging and dropping files"""

    _STATUS_COL = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Archivo", "Formato", "Duración", "Tamaño", "Estado"])
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DropOnly)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)

    def resizeEvent(self, event):
        total_width = self.viewport().width()
        self.setColumnWidth(0, int(total_width * 0.38))
        self.setColumnWidth(1, int(total_width * 0.20))
        self.setColumnWidth(2, int(total_width * 0.12))
        self.setColumnWidth(3, int(total_width * 0.10))
        self.setColumnWidth(4, int(total_width * 0.18))
        super().resizeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if os.path.isfile(f) and is_video_file(f)]
        existing_files = [self.item(row, 0).data(Qt.UserRole) for row in range(self.rowCount())
                          if self.item(row, 0) is not None]
        for file in valid_files:
            if file not in existing_files:
                self.add_file(file)
        event.acceptProposedAction()

    def add_file(self, file_path):
        codec = get_video_codec(file_path)
        compatibility = "Compatible con TVs" if codec.lower() in ['h264', 'hevc', 'mpeg4'] else "Baja compatibilidad TV"
        format_info = f"{codec} ({compatibility})"
        duration = get_video_duration(file_path)
        formatted_duration = format_duration(duration)
        file_size = os.path.getsize(file_path)
        formatted_size = format_size(file_size)
        row = self.rowCount()
        self.insertRow(row)
        item = QTableWidgetItem(os.path.basename(file_path))
        item.setData(Qt.UserRole, file_path)
        self.setItem(row, 0, item)
        self.setItem(row, 1, QTableWidgetItem(format_info))
        self.setItem(row, 2, QTableWidgetItem(formatted_duration))
        self.setItem(row, 3, QTableWidgetItem(formatted_size))
        self._set_status_cell(row, 'idle')

    def _row_for_file(self, file_path):
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data(Qt.UserRole) == file_path:
                return row
        return -1

    def _set_status_cell(self, row, status, progress=0):
        col = self._STATUS_COL
        if status == 'idle':
            lbl = QLabel("—")
            lbl.setAlignment(Qt.AlignCenter)
            self.setCellWidget(row, col, lbl)
        elif status == 'pending':
            lbl = QLabel("En cola")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: gray;")
            self.setCellWidget(row, col, lbl)
        elif status == 'converting':
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(progress)
            bar.setFormat(f"{progress}%")
            bar.setTextVisible(True)
            self.setCellWidget(row, col, bar)
        elif status == 'done':
            lbl = QLabel("✓ Listo")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #2ecc40; font-weight: bold;")
            self.setCellWidget(row, col, lbl)
        elif status == 'error':
            lbl = QLabel("✗ Error")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #ff4136; font-weight: bold;")
            self.setCellWidget(row, col, lbl)
        elif status == 'cancelled':
            lbl = QLabel("Cancelado")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #ff851b;")
            self.setCellWidget(row, col, lbl)

    def set_file_status(self, file_path, status, progress=0):
        """Set the status cell for a given file path."""
        row = self._row_for_file(file_path)
        if row != -1:
            self._set_status_cell(row, status, progress)

    def update_file_progress(self, file_path, progress):
        """Update the progress bar value for a file currently being converted."""
        row = self._row_for_file(file_path)
        if row == -1:
            return
        widget = self.cellWidget(row, self._STATUS_COL)
        if isinstance(widget, QProgressBar):
            widget.setValue(progress)
            widget.setFormat(f"{progress}%")
        else:
            self._set_status_cell(row, 'converting', progress)

    def reset_all_statuses(self):
        """Reset the status column for all rows to idle."""
        for row in range(self.rowCount()):
            self._set_status_cell(row, 'idle')

class ConversionThread(QThread):
    """Converts a single video file. Emits progress (0-100) and signals for done/error."""
    progress_updated  = pyqtSignal(int)   # percent complete (0-100)
    conversion_done   = pyqtSignal()       # emitted only on successful completion
    error_occurred    = pyqtSignal(str)    # emitted on ffmpeg error

    def __init__(self, file_path, output_folder, format_preset, quality_setting, encoder=ENCODER_CPU):
        super().__init__()
        self.file_path = file_path
        self.output_folder = output_folder
        self.conversion_preset = ConversionPreset(format_preset, quality_setting)
        self.encoder = encoder
        self.running = True
        self.process = None
        self.output_path = None

    def _build_output_kwargs(self, resolved_encoder, codec):
        """Build ffmpeg output keyword arguments for the resolved encoder and codec."""
        crf = self.conversion_preset.get_crf()
        base = {
            'acodec': 'aac',
            'audio_bitrate': '192k',
            'movflags': '+faststart',
            'progress': 'pipe:1',
        }
        if resolved_encoder == ENCODER_NVIDIA:
            base.update({'vcodec': codec, 'preset': 'p4', 'rc': 'vbr', 'cq': crf})
        elif resolved_encoder == ENCODER_INTEL:
            base.update({'vcodec': codec, 'global_quality': crf, 'look_ahead': '1'})
        elif resolved_encoder == ENCODER_AMD:
            base.update({'vcodec': codec, 'rc': 'cqp', 'qp_i': crf, 'qp_p': crf})
        else:
            base.update({'vcodec': codec, 'preset': 'slow', 'crf': crf})
        return base

    def run(self):
        try:
            base_name = os.path.splitext(os.path.basename(self.file_path))[0]
            container_ext = self.conversion_preset.get_container_extension()
            self.output_path = os.path.join(self.output_folder, f"{base_name}{container_ext}")

            duration = get_video_duration(self.file_path)
            resolved_encoder, vcodec = self.conversion_preset.resolve_encoder(self.encoder)

            try:
                self.process = (
                    ffmpeg
                    .input(self.file_path)
                    .output(self.output_path, **self._build_output_kwargs(resolved_encoder, vcodec))
                    .overwrite_output()
                    .run_async(pipe_stdout=True, pipe_stderr=True)
                )
            except ffmpeg.Error as e:
                self.error_occurred.emit(e.stderr.decode())
                return

            while True:
                if not self.running:
                    break
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.decode('utf-8').strip()
                if line.startswith("out_time_ms="):
                    try:
                        out_time_ms = int(line.split("=")[1])
                        if duration > 0:
                            percent = min(99, int((out_time_ms / (duration * 1000000)) * 100))
                            self.progress_updated.emit(percent)
                    except Exception:
                        pass
                elif line == "progress=end":
                    self.progress_updated.emit(100)
                    break

            self.process.wait()

            if not self.running:
                try:
                    if self.output_path and os.path.exists(self.output_path):
                        os.remove(self.output_path)
                except Exception:
                    pass
            else:
                self.conversion_done.emit()

        except Exception as e:
            self.error_occurred.emit(f"Error inesperado: {str(e)}")

    def stop(self):
        self.running = False
        try:
            if self.process is not None:
                self.process.kill()
                self.process.wait()
            if self.output_path and os.path.exists(self.output_path):
                os.remove(self.output_path)
        except Exception:
            pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.output_folder = None
        self.conversion_thread = None
        self.next_index = 0  # Next video index to convert
        self.setup_ui()
        self.setWindowTitle("Conversor de Video")
        self.load_last_state()

    def setup_ui(self):
        # Create widgets
        self.list_widget = DragDropTableWidget()
        self.btn_input_folder = QPushButton("Seleccionar carpeta de entrada")
        self.btn_output_folder = QPushButton("Seleccionar carpeta de salida")
        self.btn_start = QPushButton("Iniciar conversión")
        self.btn_start.setStyleSheet("background-color: green; color: white;")
        self.progress_bar = QProgressBar()  # Global progress
        self.file_progress_bar = QProgressBar()  # File conversion progress
        self.lbl_status = QLabel("Estado: Listo")
        # New buttons for export/import state
        self.btn_export = QPushButton("Exportar lista")
        self.btn_import = QPushButton("Cargar lista")

        # Modify quality layout: first preset combo then quality combo
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("Formato Preset:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(ConversionPreset.get_available_presets())
        quality_layout.addWidget(self.format_combo)
        quality_layout.addWidget(QLabel("Calidad de salida:"))
        self.dependent_quality_combo = QComboBox()
        self.dependent_quality_combo.addItems(ConversionPreset.get_available_qualities())
        quality_layout.addWidget(self.dependent_quality_combo)
        quality_layout.addWidget(QLabel("Encoder:"))
        self.encoder_combo = QComboBox()
        self.encoder_combo.addItems(AVAILABLE_ENCODERS)
        quality_layout.addWidget(self.encoder_combo)
        quality_layout.addWidget(self.btn_start)

        # Configure layout
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Archivos a convertir:"))
        layout.addWidget(self.list_widget)

        folder_buttons_layout = QHBoxLayout()
        folder_buttons_layout.addWidget(self.btn_input_folder)
        folder_buttons_layout.addWidget(self.btn_output_folder)
        layout.addLayout(folder_buttons_layout)

        layout.addLayout(quality_layout)

        # New layout for export/import buttons
        state_buttons_layout = QHBoxLayout()
        state_buttons_layout.addWidget(self.btn_export)
        state_buttons_layout.addWidget(self.btn_import)
        layout.addLayout(state_buttons_layout)

        layout.addWidget(self.lbl_status)
        layout.addWidget(self.file_progress_bar)
        layout.addWidget(self.progress_bar)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Connect signals
        self.btn_input_folder.clicked.connect(self.select_input_folder)
        self.btn_output_folder.clicked.connect(self.select_output_folder)
        self.btn_start.clicked.connect(self.toggle_conversion)
        self.btn_export.clicked.connect(self.export_state)
        self.btn_import.clicked.connect(self.import_state)

    def save_state_to_file(self, file_path, adjusted_next_index=None):
        root = ET.Element("app_state")
        videos_elem = ET.SubElement(root, "videos")
        for row in range(self.list_widget.rowCount()):
            item = self.list_widget.item(row, 0)
            if item:
                video_elem = ET.SubElement(videos_elem, "video")
                video_elem.text = item.data(Qt.UserRole)
        out_elem = ET.SubElement(root, "output_folder")
        out_elem.text = self.output_folder if self.output_folder else ""
        quality_elem = ET.SubElement(root, "quality")
        quality_elem.text = self.dependent_quality_combo.currentText()
        format_elem = ET.SubElement(root, "format_preset")
        format_elem.text = self.format_combo.currentText()
        encoder_elem = ET.SubElement(root, "encoder")
        encoder_elem.text = self.encoder_combo.currentText()
        index_elem = ET.SubElement(root, "next_index")
        if adjusted_next_index is not None:
            index_elem.text = str(adjusted_next_index)
        else:
            index_elem.text = str(self.next_index)
        tree = ET.ElementTree(root)
        tree.write(file_path, encoding='utf-8', xml_declaration=True)

    def load_state_from_file(self, file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            self.list_widget.setRowCount(0)
            videos = root.find('videos')
            if videos is not None:
                for video in videos.findall('video'):
                    file_path = video.text.strip()
                    if file_path and os.path.exists(file_path) and is_video_file(file_path):
                        self.list_widget.add_file(file_path)
            out_elem = root.find('output_folder')
            if out_elem is not None:
                folder = out_elem.text.strip()
                if folder and os.path.isdir(folder):
                    self.output_folder = folder
                    self.lbl_status.setText(f"Carpeta de salida: {folder}")
            quality_elem = root.find('quality')
            if quality_elem is not None:
                quality = quality_elem.text.strip()
                index = self.dependent_quality_combo.findText(quality)
                if index != -1:
                    self.dependent_quality_combo.setCurrentIndex(index)
            format_elem = root.find('format_preset')
            if format_elem is not None:
                fmt = format_elem.text.strip()
                index = self.format_combo.findText(fmt)
                if index != -1:
                    self.format_combo.setCurrentIndex(index)
            encoder_elem = root.find('encoder')
            if encoder_elem is not None:
                enc = encoder_elem.text.strip()
                idx = self.encoder_combo.findText(enc)
                if idx != -1:
                    self.encoder_combo.setCurrentIndex(idx)
            index_elem = root.find('next_index')
            if index_elem is not None:
                try:
                    self.next_index = int(index_elem.text.strip())
                except ValueError:
                    self.next_index = 0
            if self.next_index < self.list_widget.rowCount():
                self.list_widget.setCurrentCell(self.next_index, 0)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading state: {str(e)}")

    def export_state(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Exportar lista", "", "XML Files (*.xml)")
        if file_path:
            adjusted_index = None
            if self.conversion_thread and self.conversion_thread.isRunning():
                adjusted_index = max(self.next_index - 1, 0)
            self.save_state_to_file(file_path, adjusted_next_index=adjusted_index)
            QMessageBox.information(self, "Exportar lista", "Lista exportada correctamente.")

    def import_state(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Cargar lista", "", "All Files (*.xml)")
        if file_path:
            self.load_state_from_file(file_path)
            QMessageBox.information(self, "Cargar lista", "Lista cargada correctamente.")

    def load_last_state(self):
        state_file = os.path.join(os.path.dirname(__file__), 'last_state.xml')
        if os.path.exists(state_file):
            try:
                tree = ET.parse(state_file)
                root = tree.getroot()
                # Load videos
                self.list_widget.setRowCount(0)
                videos = root.find('videos')
                if videos is not None:
                    for video in videos.findall('video'):
                        file_path = video.text.strip()
                        if file_path and os.path.exists(file_path) and is_video_file(file_path):
                            self.list_widget.add_file(file_path)
                # Load output folder
                out_elem = root.find('output_folder')
                if out_elem is not None:
                    folder = out_elem.text.strip()
                    if folder and os.path.isdir(folder):
                        self.output_folder = folder
                        self.lbl_status.setText(f"Carpeta de salida: {folder}")
                # Load quality
                quality_elem = root.find('quality')
                if quality_elem is not None:
                    quality = quality_elem.text.strip()
                    index = self.dependent_quality_combo.findText(quality)
                    if index != -1:
                        self.dependent_quality_combo.setCurrentIndex(index)
                # Load format preset
                format_elem = root.find('format_preset')
                if format_elem is not None:
                    fmt = format_elem.text.strip()
                    index = self.format_combo.findText(fmt)
                    if index != -1:
                        self.format_combo.setCurrentIndex(index)
                # Load encoder
                encoder_elem = root.find('encoder')
                if encoder_elem is not None:
                    enc = encoder_elem.text.strip()
                    idx = self.encoder_combo.findText(enc)
                    if idx != -1:
                        self.encoder_combo.setCurrentIndex(idx)
                # Load next index and select that row
                index_elem = root.find('next_index')
                if index_elem is not None:
                    try:
                        self.next_index = int(index_elem.text.strip())
                    except ValueError:
                        self.next_index = 0
                if self.next_index < self.list_widget.rowCount():
                    self.list_widget.setCurrentCell(self.next_index, 0)
            except Exception:
                pass

    def select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de entrada")
        if folder:
            # Disable table and show loading indicator
            self.list_widget.setEnabled(False)
            self.lbl_status.setText("Cargando información...")
            self.list_widget.setRowCount(0)
            self.add_video_files_from_folder(folder)
            self.lbl_status.setText("Información cargada")
            self.list_widget.setEnabled(True)

    def add_video_files_from_folder(self, folder):
        video_files = []
        for root_dir, _, files in os.walk(folder):
            for file in files:
                file_path = os.path.join(root_dir, file)
                if is_video_file(file_path):
                    video_files.append(file_path)

        existing_files = [self.list_widget.item(row, 0).data(Qt.UserRole) for row in range(self.list_widget.rowCount())
                          if self.list_widget.item(row, 0) is not None]
        for file in video_files:
            if file not in existing_files:
                self.list_widget.add_file(file)
                QApplication.processEvents()

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if folder:
            self.output_folder = folder
            self.lbl_status.setText(f"Carpeta de salida: {folder}")

    def toggle_conversion(self):
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.conversion_thread.stop()
            self.progress_bar.setValue(0)
            self.file_progress_bar.setValue(0)
            self.progress_bar.setValue(0)
            self.btn_start.setText("Iniciar conversión")
            self.btn_start.setStyleSheet("background-color: green; color: white;")
            self.btn_input_folder.setEnabled(True)
            self.btn_output_folder.setEnabled(True)
            self.dependent_quality_combo.setEnabled(True)
            self.format_combo.setEnabled(True)
            self.encoder_combo.setEnabled(True)
            self.list_widget.setEnabled(True)
            self.btn_import.setEnabled(True)
            self.conversion_thread = None
        else:
            if not self.output_folder:
                QMessageBox.critical(self, "Error", "Selecciona una carpeta de salida")
                return
            if self.list_widget.rowCount() == 0:
                QMessageBox.critical(self, "Error", "Agrega archivos para convertir")
                return

            files = [self.list_widget.item(row, 0).data(Qt.UserRole) for row in range(self.list_widget.rowCount())
                     if self.list_widget.item(row, 0) is not None]
            self.conversion_thread = ConversionThread(
                files,
                self.output_folder,
                self.format_combo.currentText(),
                self.dependent_quality_combo.currentText(),
                self.encoder_combo.currentText()
            )

            self.conversion_thread.progress_updated.connect(self.update_progress)
            self.conversion_thread.file_progress_updated.connect(self.update_file_progress)
            self.conversion_thread.error_occurred.connect(self.show_error)
            self.conversion_thread.finished.connect(self.conversion_finished)

            self.btn_start.setText("Detener conversión")
            self.btn_start.setStyleSheet("background-color: yellow; color: black;")
            self.btn_input_folder.setEnabled(False)
            self.btn_output_folder.setEnabled(False)
            self.dependent_quality_combo.setEnabled(False)
            self.format_combo.setEnabled(False)
            self.encoder_combo.setEnabled(False)
            self.list_widget.setEnabled(False)
            self.btn_import.setEnabled(False)
            self.progress_bar.setValue(0)
            self.file_progress_bar.setValue(0)
            self.conversion_thread.start()

    def update_progress(self, current_file, progress):
        self.lbl_status.setText(f"Procesando: {os.path.basename(current_file)}")
        self.progress_bar.setValue(progress)

    def update_file_progress(self, current_file, progress):
        self.file_progress_bar.setValue(progress)
        # Update next_index if file conversion completes
        if progress == 100:
            for row in range(self.list_widget.rowCount()):
                item = self.list_widget.item(row, 0)
                if item and item.data(Qt.UserRole) == current_file:
                    new_index = row + 1
                    if new_index < self.list_widget.rowCount():
                        self.next_index = new_index
                    else:
                        self.next_index = row
                    break

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    def conversion_finished(self):
        self.btn_start.setText("Iniciar conversión")
        self.btn_start.setStyleSheet("background-color: green; color: white;")
        self.lbl_status.setText("Estado: Conversión completada")
        self.btn_input_folder.setEnabled(True)
        self.btn_output_folder.setEnabled(True)
        self.dependent_quality_combo.setEnabled(True)
        self.format_combo.setEnabled(True)
        self.encoder_combo.setEnabled(True)
        self.list_widget.setEnabled(True)
        self.btn_import.setEnabled(True)
        self.conversion_thread = None

    def closeEvent(self, event):
        # Show confirmation dialog on exit
        reply = QMessageBox.question(self, "Confirmar salida", "¿Estás seguro de cerrar el programa?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # If a conversion is in progress, stop it before closing
            if self.conversion_thread and self.conversion_thread.isRunning():
                self.conversion_thread.stop()
            # Save state in XML
            root = ET.Element("app_state")
            videos_elem = ET.SubElement(root, "videos")
            for row in range(self.list_widget.rowCount()):
                item = self.list_widget.item(row, 0)
                if item:
                    video_elem = ET.SubElement(videos_elem, "video")
                    video_elem.text = item.data(Qt.UserRole)
            out_elem = ET.SubElement(root, "output_folder")
            out_elem.text = self.output_folder if self.output_folder else ""
            quality_elem = ET.SubElement(root, "quality")
            quality_elem.text = self.dependent_quality_combo.currentText()
            format_elem = ET.SubElement(root, "format_preset")
            format_elem.text = self.format_combo.currentText()
            encoder_elem = ET.SubElement(root, "encoder")
            encoder_elem.text = self.encoder_combo.currentText()
            index_elem = ET.SubElement(root, "next_index")
            index_elem.text = str(self.next_index)
            tree = ET.ElementTree(root)
            state_file = os.path.join(os.path.dirname(__file__), 'last_state.xml')
            tree.write(state_file, encoding='utf-8', xml_declaration=True)
            event.accept()
        else:
            event.ignore()

    def showEvent(self, event):
        super().showEvent(event)
        # Center the window on the screen
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec_())
