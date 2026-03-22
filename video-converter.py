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
                msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
                self.error_occurred.emit(msg)
                return
            except FileNotFoundError:
                self.error_occurred.emit("ffmpeg no encontrado. Asegúrate de tenerlo instalado y en el PATH.")
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
        except Exception:
            pass
        try:
            if self.output_path and os.path.exists(self.output_path):
                os.remove(self.output_path)
        except Exception:
            pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.output_folder = None
        self.next_index = 0
        # Parallel conversion state
        self.pending_files = []          # queue of file paths waiting to start
        self.active_threads = {}         # file_path -> ConversionThread (active slots)
        self._thread_refs = set()        # keeps thread objects alive until Qt finishes them
        self.completed_file_paths = set()
        self.total_count = 0
        self.setup_ui()
        self.setWindowTitle("Conversor de Video")
        self.load_last_state()

    def setup_ui(self):
        self.list_widget = DragDropTableWidget()
        self.btn_input_folder = QPushButton("Seleccionar carpeta de entrada")
        self.btn_output_folder = QPushButton("Seleccionar carpeta de salida")
        self.btn_start = QPushButton("Iniciar conversión")
        self.btn_start.setStyleSheet("background-color: green; color: white;")
        self.progress_bar = QProgressBar()
        self.lbl_status = QLabel("Estado: Listo")
        self.btn_export = QPushButton("Exportar lista")
        self.btn_import = QPushButton("Cargar lista")

        # Controls row
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Formato:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(ConversionPreset.get_available_presets())
        controls_layout.addWidget(self.format_combo)
        controls_layout.addWidget(QLabel("Calidad:"))
        self.dependent_quality_combo = QComboBox()
        self.dependent_quality_combo.addItems(ConversionPreset.get_available_qualities())
        controls_layout.addWidget(self.dependent_quality_combo)
        controls_layout.addWidget(QLabel("Encoder:"))
        self.encoder_combo = QComboBox()
        self.encoder_combo.addItems(AVAILABLE_ENCODERS)
        controls_layout.addWidget(self.encoder_combo)
        controls_layout.addWidget(QLabel("Paralelo:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 5)
        self.parallel_spin.setValue(2)
        self.parallel_spin.setToolTip("Número de archivos a convertir simultáneamente (1–5)")
        controls_layout.addWidget(self.parallel_spin)
        controls_layout.addWidget(self.btn_start)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Archivos a convertir:"))
        layout.addWidget(self.list_widget)

        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.btn_input_folder)
        folder_layout.addWidget(self.btn_output_folder)
        layout.addLayout(folder_layout)
        layout.addLayout(controls_layout)

        state_layout = QHBoxLayout()
        state_layout.addWidget(self.btn_export)
        state_layout.addWidget(self.btn_import)
        layout.addLayout(state_layout)

        layout.addWidget(self.lbl_status)
        layout.addWidget(self.progress_bar)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.btn_input_folder.clicked.connect(self.select_input_folder)
        self.btn_output_folder.clicked.connect(self.select_output_folder)
        self.btn_start.clicked.connect(self.toggle_conversion)
        self.btn_export.clicked.connect(self.export_state)
        self.btn_import.clicked.connect(self.import_state)

    # ------------------------------------------------------------------ #
    #  Parallel conversion coordinator                                     #
    # ------------------------------------------------------------------ #

    def toggle_conversion(self):
        if self.active_threads or self.pending_files:
            # Stop everything
            self.pending_files.clear()
            for fp, thread in list(self.active_threads.items()):
                thread.stop()
                self.list_widget.set_file_status(fp, 'cancelled')
            self.active_threads.clear()
            self.progress_bar.setValue(0)
            self.lbl_status.setText("Estado: Cancelado")
            self.btn_start.setText("Iniciar conversión")
            self.btn_start.setStyleSheet("background-color: green; color: white;")
            self._set_controls_enabled(True)
        else:
            if not self.output_folder:
                QMessageBox.critical(self, "Error", "Selecciona una carpeta de salida")
                return
            if self.list_widget.rowCount() == 0:
                QMessageBox.critical(self, "Error", "Agrega archivos para convertir")
                return

            all_files = [
                self.list_widget.item(row, 0).data(Qt.UserRole)
                for row in range(self.list_widget.rowCount())
                if self.list_widget.item(row, 0)
            ]
            files_to_convert = all_files[self.next_index:]
            if not files_to_convert:
                QMessageBox.information(self, "Info", "Todos los archivos ya han sido procesados.")
                return

            self.pending_files = files_to_convert[:]
            self.total_count = len(files_to_convert)
            self.completed_file_paths = set()

            for fp in files_to_convert:
                self.list_widget.set_file_status(fp, 'pending')

            self._set_controls_enabled(False)
            self.btn_start.setText("Detener conversión")
            self.btn_start.setStyleSheet("background-color: yellow; color: black;")
            self.progress_bar.setValue(0)
            self._launch_next_batch()

    def _launch_next_batch(self):
        """Fill available parallel slots from the pending queue."""
        max_parallel = self.parallel_spin.value()
        while len(self.active_threads) < max_parallel and self.pending_files:
            fp = self.pending_files.pop(0)
            thread = ConversionThread(
                fp,
                self.output_folder,
                self.format_combo.currentText(),
                self.dependent_quality_combo.currentText(),
                self.encoder_combo.currentText()
            )
            thread.progress_updated.connect(lambda p, f=fp: self._on_file_progress(f, p))
            thread.conversion_done.connect(lambda f=fp: self._on_file_done(f))
            thread.error_occurred.connect(lambda err, f=fp: self._on_file_error(f, err))
            # Keep a reference until Qt's own finished signal fires — prevents
            # "QThread: Destroyed while thread is still running" crash.
            self._thread_refs.add(thread)
            thread.finished.connect(lambda t=thread: self._thread_refs.discard(t))
            self.active_threads[fp] = thread
            self.list_widget.set_file_status(fp, 'converting', 0)
            thread.start()
        self._update_status_label()

    def _on_file_progress(self, file_path, percent):
        self.list_widget.update_file_progress(file_path, percent)

    def _on_file_done(self, file_path):
        self.active_threads.pop(file_path, None)
        self.completed_file_paths.add(file_path)
        self.list_widget.set_file_status(file_path, 'done')
        # Advance next_index to the first not-yet-completed row
        for row in range(self.list_widget.rowCount()):
            item = self.list_widget.item(row, 0)
            if item and item.data(Qt.UserRole) not in self.completed_file_paths:
                self.next_index = row
                break
        else:
            self.next_index = self.list_widget.rowCount()

        done = len(self.completed_file_paths)
        self.progress_bar.setValue(int(done / self.total_count * 100))

        if self.pending_files or self.active_threads:
            self._launch_next_batch()
        else:
            self._conversion_all_done()

    def _on_file_error(self, file_path, error_msg):
        self.active_threads.pop(file_path, None)
        self.list_widget.set_file_status(file_path, 'error')
        QMessageBox.critical(self, "Error de conversión",
                             f"{os.path.basename(file_path)}:\n{error_msg}")
        if self.pending_files or self.active_threads:
            self._launch_next_batch()
        else:
            self._conversion_all_done()

    def _update_status_label(self):
        active = len(self.active_threads)
        done = len(self.completed_file_paths)
        total = self.total_count
        pending = len(self.pending_files)
        self.lbl_status.setText(
            f"Convirtiendo: {active} activo(s)  ·  {done}/{total} completados  ·  {pending} en cola"
        )

    def _conversion_all_done(self):
        done = len(self.completed_file_paths)
        self.btn_start.setText("Iniciar conversión")
        self.btn_start.setStyleSheet("background-color: green; color: white;")
        self.lbl_status.setText(f"Estado: Completado — {done} archivo(s) convertido(s)")
        self.progress_bar.setValue(100)
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled):
        self.btn_input_folder.setEnabled(enabled)
        self.btn_output_folder.setEnabled(enabled)
        self.dependent_quality_combo.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.encoder_combo.setEnabled(enabled)
        self.parallel_spin.setEnabled(enabled)
        self.list_widget.setEnabled(enabled)
        self.btn_import.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    #  State persistence                                                   #
    # ------------------------------------------------------------------ #

    def save_state_to_file(self, file_path):
        root = ET.Element("app_state")
        videos_elem = ET.SubElement(root, "videos")
        for row in range(self.list_widget.rowCount()):
            item = self.list_widget.item(row, 0)
            if item:
                video_elem = ET.SubElement(videos_elem, "video")
                video_elem.text = item.data(Qt.UserRole)
        ET.SubElement(root, "output_folder").text = self.output_folder or ""
        ET.SubElement(root, "quality").text = self.dependent_quality_combo.currentText()
        ET.SubElement(root, "format_preset").text = self.format_combo.currentText()
        ET.SubElement(root, "encoder").text = self.encoder_combo.currentText()
        ET.SubElement(root, "parallel_count").text = str(self.parallel_spin.value())
        ET.SubElement(root, "next_index").text = str(self.next_index)
        ET.ElementTree(root).write(file_path, encoding='utf-8', xml_declaration=True)

    def _apply_state_xml(self, root):
        """Apply an already-parsed XML root element to the UI."""
        self.list_widget.setRowCount(0)
        videos = root.find('videos')
        if videos is not None:
            for video in videos.findall('video'):
                fp = video.text.strip()
                if fp and os.path.exists(fp) and is_video_file(fp):
                    self.list_widget.add_file(fp)
        out_elem = root.find('output_folder')
        if out_elem is not None:
            folder = out_elem.text.strip()
            if folder and os.path.isdir(folder):
                self.output_folder = folder
                self.lbl_status.setText(f"Carpeta de salida: {folder}")
        for tag, combo in [('quality', self.dependent_quality_combo),
                            ('format_preset', self.format_combo),
                            ('encoder', self.encoder_combo)]:
            elem = root.find(tag)
            if elem is not None:
                idx = combo.findText(elem.text.strip())
                if idx != -1:
                    combo.setCurrentIndex(idx)
        pc_elem = root.find('parallel_count')
        if pc_elem is not None:
            try:
                self.parallel_spin.setValue(int(pc_elem.text.strip()))
            except ValueError:
                pass
        idx_elem = root.find('next_index')
        if idx_elem is not None:
            try:
                self.next_index = int(idx_elem.text.strip())
            except ValueError:
                self.next_index = 0
        if self.next_index < self.list_widget.rowCount():
            self.list_widget.setCurrentCell(self.next_index, 0)

    def load_state_from_file(self, file_path):
        try:
            tree = ET.parse(file_path)
            self._apply_state_xml(tree.getroot())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar estado: {str(e)}")

    def export_state(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Exportar lista", "", "XML Files (*.xml)")
        if file_path:
            self.save_state_to_file(file_path)
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
                self._apply_state_xml(tree.getroot())
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  Folder / file management                                            #
    # ------------------------------------------------------------------ #

    def select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de entrada")
        if folder:
            self.list_widget.setEnabled(False)
            self.lbl_status.setText("Cargando información...")
            self.list_widget.setRowCount(0)
            self.add_video_files_from_folder(folder)
            self.lbl_status.setText("Información cargada")
            self.list_widget.setEnabled(True)

    def add_video_files_from_folder(self, folder):
        existing_files = {
            self.list_widget.item(row, 0).data(Qt.UserRole)
            for row in range(self.list_widget.rowCount())
            if self.list_widget.item(row, 0)
        }
        for root_dir, _, files in os.walk(folder):
            for file in files:
                fp = os.path.join(root_dir, file)
                if is_video_file(fp) and fp not in existing_files:
                    self.list_widget.add_file(fp)
                    existing_files.add(fp)
                    QApplication.processEvents()

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if folder:
            self.output_folder = folder
            self.lbl_status.setText(f"Carpeta de salida: {folder}")

    # ------------------------------------------------------------------ #
    #  Window events                                                       #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event):
        reply = QMessageBox.question(self, "Confirmar salida", "¿Estás seguro de cerrar el programa?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.pending_files.clear()
            for thread in list(self.active_threads.values()):
                thread.stop()
            # Wait for each thread to finish cleanly before the app exits
            for thread in list(self.active_threads.values()):
                thread.wait(5000)
            self.active_threads.clear()
            state_file = os.path.join(os.path.dirname(__file__), 'last_state.xml')
            self.save_state_to_file(state_file)
            event.accept()
        else:
            event.ignore()

    def showEvent(self, event):
        super().showEvent(event)
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
