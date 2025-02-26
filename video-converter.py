import os
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton, QComboBox, QProgressBar, QLabel,
                             QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import ffmpeg

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


class DragDropTableWidget(QTableWidget):
    """Custom TableWidget for dragging and dropping files"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["File", "Format"])
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DropOnly)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if os.path.isfile(f) and is_video_file(f)]
        existing_files = [self.item(row, 0).text() for row in range(self.rowCount())
                          if self.item(row, 0) is not None]
        for file in valid_files:
            if file not in existing_files:
                self.add_file(file)
        event.acceptProposedAction()

    def add_file(self, file_path):
        # Auto-detect video codec and determine TV compatibility
        codec = get_video_codec(file_path)
        compatibility = "Compatible with old TVs" if codec.lower() in ['h264', 'hevc', 'mpeg4'] else "Not very compatible with old TVs"
        format_info = f"{codec} ({compatibility})"
        row = self.rowCount()
        self.insertRow(row)
        self.setItem(row, 0, QTableWidgetItem(file_path))
        self.setItem(row, 1, QTableWidgetItem(format_info))


class ConversionThread(QThread):
    progress_updated = pyqtSignal(str, int)
    file_progress_updated = pyqtSignal(str, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, files, output_folder, quality):
        super().__init__()
        self.files = files
        self.output_folder = output_folder
        self.quality = quality
        self.running = True

    def get_crf(self):
        """Gets the CRF value based on the selected quality"""
        return {
            "Baja": "28",
            "Media": "23",
            "Alta": "18"
        }.get(self.quality, "23")

    def run(self):
        try:
            total_files = len(self.files)
            for index, file_path in enumerate(self.files):
                if not self.running:
                    break

                # Generate output file name
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                output_path = os.path.join(self.output_folder, f"{base_name}.mp4")

                # Update global progress before starting file conversion
                self.progress_updated.emit(file_path, int((index / total_files) * 100))

                # Get video duration for current file
                duration = get_video_duration(file_path)
                self.file_progress_updated.emit(file_path, 0)

                try:
                    process = (
                        ffmpeg
                        .input(file_path)
                        .output(output_path,
                                vcodec='libx264',
                                preset='slow',
                                crf=self.get_crf(),
                                acodec='aac',
                                audio_bitrate='192k',
                                movflags='+faststart',
                                progress='pipe:1')
                        .overwrite_output()
                        .run_async(pipe_stdout=True, pipe_stderr=True)
                    )
                except ffmpeg.Error as e:
                    self.error_occurred.emit(f"Error converting {file_path}: {e.stderr.decode()}")
                    continue

                # Read progress information from ffmpeg output
                while True:
                    line = process.stdout.readline()
                    if not line:
                        break
                    line = line.decode('utf-8').strip()
                    if line.startswith("out_time_ms="):
                        try:
                            out_time_ms = int(line.split("=")[1])
                            if duration > 0:
                                percent_file = min(100, int((out_time_ms / (duration * 1000000)) * 100))
                                self.file_progress_updated.emit(file_path, percent_file)
                        except Exception:
                            pass
                    if line.startswith("progress="):
                        if line.split("=")[1] == "end":
                            self.file_progress_updated.emit(file_path, 100)
                            break
                process.wait()

                # Update global progress after file conversion
                self.progress_updated.emit(file_path, int(((index + 1) / total_files) * 100))

            self.progress_updated.emit("Conversion completed", 100)
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {str(e)}")

    def stop(self):
        self.running = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.output_folder = None
        self.conversion_thread = None
        self.setup_ui()
        self.setWindowTitle("Conversor de Video")

    def setup_ui(self):
        # Create widgets
        self.list_widget = DragDropTableWidget()
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Baja", "Media", "Alta"])
        self.btn_input_folder = QPushButton("Seleccionar carpeta de entrada")
        self.btn_output_folder = QPushButton("Seleccionar carpeta de salida")
        self.btn_start = QPushButton("Iniciar conversión")
        self.progress_bar = QProgressBar()  # Global progress
        self.file_progress_bar = QProgressBar()  # File conversion progress
        self.lbl_status = QLabel("Estado: Listo")

        # Configure layout
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Archivos a convertir:"))
        layout.addWidget(self.list_widget)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.btn_input_folder)
        buttons_layout.addWidget(self.btn_output_folder)
        layout.addLayout(buttons_layout)

        layout.addWidget(QLabel("Calidad de salida:"))
        layout.addWidget(self.quality_combo)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.file_progress_bar)
        layout.addWidget(self.btn_start)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Connect signals
        self.btn_input_folder.clicked.connect(self.select_input_folder)
        self.btn_output_folder.clicked.connect(self.select_output_folder)
        self.btn_start.clicked.connect(self.toggle_conversion)

    def select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de entrada")
        if folder:
            self.list_widget.setRowCount(0)
            self.add_video_files_from_folder(folder)

    def add_video_files_from_folder(self, folder):
        video_files = []
        for root, _, files in os.walk(folder):
            for file in files:
                file_path = os.path.join(root, file)
                if is_video_file(file_path):
                    video_files.append(file_path)

        existing_files = [self.list_widget.item(row, 0).text() for row in range(self.list_widget.rowCount())
                          if self.list_widget.item(row, 0) is not None]
        for file in video_files:
            if file not in existing_files:
                self.list_widget.add_file(file)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if folder:
            self.output_folder = folder
            self.lbl_status.setText(f"Carpeta de salida: {folder}")

    def toggle_conversion(self):
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.conversion_thread.stop()
            self.btn_start.setText("Iniciar conversión")
            self.conversion_thread = None
        else:
            if not self.output_folder:
                QMessageBox.critical(self, "Error", "Selecciona una carpeta de salida")
                return
            if self.list_widget.rowCount() == 0:
                QMessageBox.critical(self, "Error", "Agrega archivos para convertir")
                return

            files = [self.list_widget.item(row, 0).text() for row in range(self.list_widget.rowCount())
                     if self.list_widget.item(row, 0) is not None]
            self.conversion_thread = ConversionThread(
                files,
                self.output_folder,
                self.quality_combo.currentText()
            )

            self.conversion_thread.progress_updated.connect(self.update_progress)
            self.conversion_thread.file_progress_updated.connect(self.update_file_progress)
            self.conversion_thread.error_occurred.connect(self.show_error)
            self.conversion_thread.finished.connect(self.conversion_finished)

            self.btn_start.setText("Detener conversión")
            self.progress_bar.setValue(0)
            self.file_progress_bar.setValue(0)
            self.conversion_thread.start()

    def update_progress(self, current_file, progress):
        self.lbl_status.setText(f"Procesando: {os.path.basename(current_file)}")
        self.progress_bar.setValue(progress)

    def update_file_progress(self, current_file, progress):
        self.file_progress_bar.setValue(progress)

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    def conversion_finished(self):
        self.btn_start.setText("Iniciar conversión")
        self.lbl_status.setText("Estado: Conversión completada")
        self.conversion_thread = None

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
