import os
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QComboBox, QProgressBar, QLabel,
                             QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import ffmpeg

# Lista de extensiones de video soportadas
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp']


def is_video_file(file_path):
    """Verifica si un archivo es un video según su extensión"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_EXTENSIONS


class DragDropListWidget(QListWidget):
    """ListWidget personalizado para arrastrar y soltar archivos"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if os.path.isfile(f) and is_video_file(f)]

        existing_items = {self.item(i).text() for i in range(self.count())}
        new_files = [f for f in valid_files if f not in existing_items]

        self.addItems(new_files)
        event.acceptProposedAction()


class ConversionThread(QThread):
    progress_updated = pyqtSignal(str, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, files, output_folder, quality):
        super().__init__()
        self.files = files
        self.output_folder = output_folder
        self.quality = quality
        self.running = True

    def get_crf(self):
        """Obtiene el valor CRF según la calidad seleccionada"""
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

                # Generar nombre de archivo de salida
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                output_path = os.path.join(self.output_folder, f"{base_name}.mp4")

                # Actualizar interfaz
                self.progress_updated.emit(file_path, int((index / total_files) * 100))

                # Configurar parámetros de conversión
                crf = self.get_crf()

                try:
                    (
                        ffmpeg
                        .input(file_path)
                        .output(output_path,
                                vcodec='libx264',
                                preset='slow',
                                crf=crf,
                                acodec='aac',
                                audio_bitrate='192k',
                                movflags='+faststart')
                        .overwrite_output()
                        .run(quiet=True)
                    )
                except ffmpeg.Error as e:
                    self.error_occurred.emit(f"Error al convertir {file_path}: {e.stderr.decode()}")

                # Actualizar progreso
                self.progress_updated.emit(file_path, int(((index + 1) / total_files) * 100))

            self.progress_updated.emit("Conversión completada", 100)
        except Exception as e:
            self.error_occurred.emit(f"Error inesperado: {str(e)}")

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
        # Crear widgets
        self.list_widget = DragDropListWidget()
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Baja", "Media", "Alta"])
        self.btn_input_folder = QPushButton("Seleccionar carpeta de entrada")
        self.btn_output_folder = QPushButton("Seleccionar carpeta de salida")
        self.btn_start = QPushButton("Iniciar conversión")
        self.progress_bar = QProgressBar()
        self.lbl_status = QLabel("Estado: Listo")

        # Configurar layout
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
        layout.addWidget(self.btn_start)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Conectar señales
        self.btn_input_folder.clicked.connect(self.select_input_folder)
        self.btn_output_folder.clicked.connect(self.select_output_folder)
        self.btn_start.clicked.connect(self.toggle_conversion)

    def select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de entrada")
        if folder:
            self.list_widget.clear()
            self.add_video_files_from_folder(folder)

    def add_video_files_from_folder(self, folder):
        video_files = []
        for root, _, files in os.walk(folder):
            for file in files:
                file_path = os.path.join(root, file)
                if is_video_file(file_path):
                    video_files.append(file_path)

        existing_items = {self.list_widget.item(i).text() for i in range(self.list_widget.count())}
        new_files = [f for f in video_files if f not in existing_items]
        self.list_widget.addItems(new_files)

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
            if self.list_widget.count() == 0:
                QMessageBox.critical(self, "Error", "Agrega archivos para convertir")
                return

            files = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
            self.conversion_thread = ConversionThread(
                files,
                self.output_folder,
                self.quality_combo.currentText()
            )

            self.conversion_thread.progress_updated.connect(self.update_progress)
            self.conversion_thread.error_occurred.connect(self.show_error)
            self.conversion_thread.finished.connect(self.conversion_finished)

            self.btn_start.setText("Detener conversión")
            self.progress_bar.setValue(0)
            self.conversion_thread.start()

    def update_progress(self, current_file, progress):
        self.lbl_status.setText(f"Procesando: {os.path.basename(current_file)}")
        self.progress_bar.setValue(progress)

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    def conversion_finished(self):
        self.btn_start.setText("Iniciar conversión")
        self.lbl_status.setText("Estado: Conversión completada")
        self.conversion_thread = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec_())