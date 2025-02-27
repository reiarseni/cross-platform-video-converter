import os
import sys
import xml.etree.ElementTree as ET
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
    def __init__(self, format_preset: str, quality: str):
        self.format_preset = format_preset
        self.quality = quality

    def get_crf(self) -> str:
        """Returns the CRF value based on the selected format preset and quality."""
        preset_quality_mapping = {
            "MP4 (H.264)": {"Baja": "28", "Media": "23", "Alta": "18"},
            "MP4 (H.265)": {"Baja": "30", "Media": "25", "Alta": "20"},
            "AVI (MPEG-4)": {"Baja": "32", "Media": "27", "Alta": "22"},
            "MKV (H.264)": {"Baja": "28", "Media": "23", "Alta": "18"}
        }
        return preset_quality_mapping.get(self.format_preset, {}).get(self.quality, "23")

    def get_container_extension(self) -> str:
        """Returns the container extension based on the selected format preset."""
        container_mapping = {
            "MP4 (H.264)": ".mp4",
            "MP4 (H.265)": ".mp4",
            "AVI (MPEG-4)": ".avi",
            "MKV (H.264)": ".mkv"
        }
        return container_mapping.get(self.format_preset, ".mp4")

    def get_video_codec(self) -> str:
        """Returns the video codec based on the selected format preset."""
        vcodec_mapping = {
            "MP4 (H.264)": "libx264",
            "MP4 (H.265)": "libx265",
            "AVI (MPEG-4)": "mpeg4",
            "MKV (H.264)": "libx264"
        }
        return vcodec_mapping.get(self.format_preset, "libx264")

class DragDropTableWidget(QTableWidget):
    """Custom TableWidget for dragging and dropping files"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["File", "Format", "Video Duration", "Video Size"])
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DropOnly)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)

    def resizeEvent(self, event):
        # Adjust column widths: first column gets 50% of the table width,
        # and the remaining 3 columns share the other 50% equally.
        total_width = self.viewport().width()
        col0_width = int(total_width * 0.5)
        other_width = int((total_width * 0.5) / 3)
        self.setColumnWidth(0, col0_width)
        self.setColumnWidth(1, other_width)
        self.setColumnWidth(2, other_width)
        self.setColumnWidth(3, other_width)
        super().resizeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Accept drag move events to ensure proper drag and drop functionality.
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
        # Auto-detect video codec and determine TV compatibility
        codec = get_video_codec(file_path)
        compatibility = "Compatible with old TVs" if codec.lower() in ['h264', 'hevc', 'mpeg4'] else "Not very compatible with old TVs"
        format_info = f"{codec} ({compatibility})"
        duration = get_video_duration(file_path)
        formatted_duration = format_duration(duration)
        file_size = os.path.getsize(file_path)
        formatted_size = format_size(file_size)
        row = self.rowCount()
        self.insertRow(row)
        # Store full file path in user role and display only the basename
        item = QTableWidgetItem(os.path.basename(file_path))
        item.setData(Qt.UserRole, file_path)
        self.setItem(row, 0, item)
        self.setItem(row, 1, QTableWidgetItem(format_info))
        self.setItem(row, 2, QTableWidgetItem(formatted_duration))
        self.setItem(row, 3, QTableWidgetItem(formatted_size))

class ConversionThread(QThread):
    progress_updated = pyqtSignal(str, int)
    file_progress_updated = pyqtSignal(str, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, files, output_folder, format_preset, quality_setting):
        super().__init__()
        self.files = files
        self.output_folder = output_folder
        self.conversion_preset = ConversionPreset(format_preset, quality_setting)
        self.running = True
        self.process = None
        self.current_output_path = None

    def run(self):
        try:
            total_files = len(self.files)
            for index, file_path in enumerate(self.files):
                if not self.running:
                    break

                # Generate output file name based on selected container
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                container_ext = self.conversion_preset.get_container_extension()
                output_path = os.path.join(self.output_folder, f"{base_name}{container_ext}")
                self.current_output_path = output_path  # Store current output file path

                # Update global progress before starting file conversion
                self.progress_updated.emit(file_path, int((index / total_files) * 100))

                # Get video duration for current file
                duration = get_video_duration(file_path)
                self.file_progress_updated.emit(file_path, 0)

                # Determine video codec based on preset
                vcodec = self.conversion_preset.get_video_codec()

                try:
                    self.process = (
                        ffmpeg
                        .input(file_path)
                        .output(output_path,
                                vcodec=vcodec,
                                preset='slow',
                                crf=self.conversion_preset.get_crf(),
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
                                percent_file = min(100, int((out_time_ms / (duration * 1000000)) * 100))
                                self.file_progress_updated.emit(file_path, percent_file)
                        except Exception:
                            pass
                    if line.startswith("progress="):
                        if line.split("=")[1] == "end":
                            self.file_progress_updated.emit(file_path, 100)
                            break
                self.process.wait()

                # If conversion was stopped, attempt to remove incomplete output file
                if not self.running:
                    try:
                        if os.path.exists(output_path):
                            os.remove(output_path)
                    except Exception as e:
                        self.error_occurred.emit(f"Error removing incomplete file {output_path}: {str(e)}")
                    break

                # Update global progress after file conversion
                self.progress_updated.emit(file_path, int(((index + 1) / total_files) * 100))

            self.progress_updated.emit("Conversion completed", 100)
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {str(e)}")

    def stop(self):
        self.running = False
        try:
            if self.process is not None:
                self.process.kill()
                self.process.wait()
            if self.current_output_path and os.path.exists(self.current_output_path):
                os.remove(self.current_output_path)
        except Exception as e:
            self.error_occurred.emit(f"Error stopping conversion: {str(e)}")
        finally:
            self.progress_updated.emit("Conversion cancelled", 0)
            self.file_progress_updated.emit("Conversion cancelled", 0)

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

        # Modify quality layout: add dependent quality and format preset selects
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("Calidad de salida:"))
        self.dependent_quality_combo = QComboBox()
        self.dependent_quality_combo.addItems(["Baja", "Media", "Alta"])
        quality_layout.addWidget(self.dependent_quality_combo)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4 (H.264)", "MP4 (H.265)", "AVI (MPEG-4)", "MKV (H.264)"])
        quality_layout.addWidget(self.format_combo)
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
                self.dependent_quality_combo.currentText()
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
