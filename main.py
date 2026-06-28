import os
import sys

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QComboBox,
    QProgressBar,
    QLabel,
    QFileDialog,
    QMessageBox,
    QSpinBox,
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices

from vconv.config import _get_app_data_dir, VIDEO_EXTENSIONS
from vconv.presets import ConversionPreset
from vconv.probing import is_video_file, get_video_codec, get_video_duration, format_duration, format_size
from vconv.conversion import ConversionThread, compute_global_progress
from vconv.ffmpeg_runtime import AVAILABLE_ENCODERS
import vconv.state as vstate

_STATUS_GLYPH = {
    "queued": "⏳",
    "converting": "▶",
    "done": "✓",
    "failed": "✗",
}


class DragDropTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(
            ["File", "Format", "Video Duration", "Video Size", "Status", ""]
        )
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DropOnly)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)

    def resizeEvent(self, event):
        total_width = self.viewport().width()
        col0_width = int(total_width * 0.5)
        other_width = int((total_width * 0.5) / 4)
        self.setColumnWidth(0, col0_width)
        self.setColumnWidth(1, other_width)
        self.setColumnWidth(2, other_width)
        self.setColumnWidth(3, other_width)
        self.setColumnWidth(4, 40)
        self.setColumnWidth(5, 40)
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
        existing_files = [
            self.item(row, 0).data(Qt.UserRole)
            for row in range(self.rowCount())
            if self.item(row, 0) is not None
        ]
        for file in valid_files:
            if file not in existing_files:
                self.add_file(file)
        event.acceptProposedAction()

    def add_file(self, file_path):
        codec = get_video_codec(file_path)
        compatibility = (
            "Compatible with old TVs"
            if codec.lower() in ["h264", "hevc", "mpeg4"]
            else "Not very compatible with old TVs"
        )
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
        duration_item = QTableWidgetItem(formatted_duration)
        duration_item.setData(Qt.UserRole, duration)  # raw seconds for indeterminate bar
        self.setItem(row, 2, duration_item)
        self.setItem(row, 3, QTableWidgetItem(formatted_size))
        status_item = QTableWidgetItem("")
        status_item.setTextAlignment(Qt.AlignCenter)
        self.setItem(row, 4, status_item)
        btn = QPushButton("✕")
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda _, b=btn: self._remove_row_for_button(b))
        self.setCellWidget(row, 5, btn)

    def _remove_row_for_button(self, button):
        for row in range(self.rowCount()):
            if self.cellWidget(row, 5) is button:
                self.removeRow(row)
                break


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.output_folder = None
        self.conversion_thread = None
        self.next_index = 0
        self.total_files = 0
        self._error_buffer = []   # [(file_basename, reason)] accumulated during a batch
        self._file_durations = [] # raw durations (seconds) matching the files list
        self.setup_ui()
        self.setWindowTitle("Conversor de Video")
        self.load_last_state()

    def setup_ui(self):
        self.list_widget = DragDropTableWidget()
        self.btn_input_folder = QPushButton("Seleccionar carpeta de entrada")
        self.btn_output_folder = QPushButton("Seleccionar carpeta de salida")
        self.btn_add_files = QPushButton("Agregar archivos")
        self.btn_start = QPushButton("Iniciar conversión")
        self.btn_start.setStyleSheet("background-color: green; color: white;")
        self.progress_bar = QProgressBar()
        self.file_progress_bar = QProgressBar()
        self.lbl_status = QLabel("Estado: Listo")
        self.btn_export = QPushButton("Exportar lista")
        self.btn_import = QPushButton("Cargar lista")
        self.btn_open_output = QPushButton("Abrir carpeta de salida")

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
        quality_layout.addWidget(QLabel("Volumen:"))
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(0, 400)
        self.volume_spin.setValue(0)
        self.volume_spin.setSuffix("%")
        self.volume_spin.setSpecialValueText("Sin boost")
        self.volume_spin.setToolTip(
            "0 = sin cambio de volumen\n"
            "100% = volumen original\n"
            "200% = doble de volumen\n"
            "400% = cuádruple (se aplica limitador para evitar distorsión)"
        )
        quality_layout.addWidget(self.volume_spin)
        quality_layout.addWidget(self.btn_start)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Archivos a convertir:"))
        layout.addWidget(self.list_widget)

        folder_buttons_layout = QHBoxLayout()
        folder_buttons_layout.addWidget(self.btn_add_files)
        folder_buttons_layout.addWidget(self.btn_input_folder)
        folder_buttons_layout.addWidget(self.btn_output_folder)
        layout.addLayout(folder_buttons_layout)

        layout.addLayout(quality_layout)

        state_buttons_layout = QHBoxLayout()
        state_buttons_layout.addWidget(self.btn_export)
        state_buttons_layout.addWidget(self.btn_import)
        state_buttons_layout.addWidget(self.btn_open_output)
        state_buttons_layout.addStretch()
        layout.addLayout(state_buttons_layout)

        layout.addWidget(self.lbl_status)
        layout.addWidget(self.file_progress_bar)
        layout.addWidget(self.progress_bar)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.btn_input_folder.clicked.connect(self.select_input_folder)
        self.btn_output_folder.clicked.connect(self.select_output_folder)
        self.btn_add_files.clicked.connect(self.add_individual_files)
        self.btn_start.clicked.connect(self.toggle_conversion)
        self.btn_export.clicked.connect(self.export_state)
        self.btn_import.clicked.connect(self.import_state)
        self.btn_open_output.clicked.connect(self.open_output_folder)

    # ------------------------------------------------------------------
    # State mappers
    # ------------------------------------------------------------------

    def _state_from_widgets(self, adjusted_next_index=None) -> vstate.AppState:
        files = [
            self.list_widget.item(row, 0).data(Qt.UserRole)
            for row in range(self.list_widget.rowCount())
            if self.list_widget.item(row, 0) is not None
        ]
        return vstate.AppState(
            files=files,
            output_folder=self.output_folder or "",
            format_preset=self.format_combo.currentText(),
            quality=self.dependent_quality_combo.currentText(),
            encoder=self.encoder_combo.currentText(),
            volume_boost=self.volume_spin.value(),
            next_index=adjusted_next_index if adjusted_next_index is not None else self.next_index,
        )

    def _apply_state_to_widgets(self, state: vstate.AppState):
        self.list_widget.setRowCount(0)
        for path in state.files:
            self.list_widget.add_file(path)

        if state.output_folder and os.path.isdir(state.output_folder):
            self.output_folder = state.output_folder
            self.lbl_status.setText(f"Carpeta de salida: {state.output_folder}")

        idx = self.dependent_quality_combo.findText(state.quality)
        if idx != -1:
            self.dependent_quality_combo.setCurrentIndex(idx)

        idx = self.format_combo.findText(state.format_preset)
        if idx != -1:
            self.format_combo.setCurrentIndex(idx)

        idx = self.encoder_combo.findText(state.encoder)
        if idx != -1:
            self.encoder_combo.setCurrentIndex(idx)

        self.volume_spin.setValue(state.volume_boost)
        self.next_index = state.next_index

        if self.next_index < self.list_widget.rowCount():
            self.list_widget.setCurrentCell(self.next_index, 0)

    # ------------------------------------------------------------------
    # Save / load through vconv.state
    # ------------------------------------------------------------------

    def save_state_to_file(self, file_path, adjusted_next_index=None):
        state = self._state_from_widgets(adjusted_next_index=adjusted_next_index)
        vstate.save(state, file_path)

    def load_state_from_file(self, file_path):
        try:
            state = vstate.from_xml(file_path)
            self._apply_state_to_widgets(state)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading state: {str(e)}")

    def export_state(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar lista", "", "XML Files (*.xml)"
        )
        if file_path:
            adjusted_index = None
            if self.conversion_thread and self.conversion_thread.isRunning():
                adjusted_index = max(self.next_index - 1, 0)
            self.save_state_to_file(file_path, adjusted_next_index=adjusted_index)
            QMessageBox.information(self, "Exportar lista", "Lista exportada correctamente.")

    def import_state(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Cargar lista", "", "All Files (*.xml)"
        )
        if file_path:
            self.load_state_from_file(file_path)
            QMessageBox.information(self, "Cargar lista", "Lista cargada correctamente.")

    def load_last_state(self):
        state_file = os.path.join(_get_app_data_dir(), "last_state.xml")
        if os.path.exists(state_file):
            try:
                state = vstate.from_xml(state_file)
                self._apply_state_to_widgets(state)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------

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
        video_files = []
        for root_dir, _, files in os.walk(folder):
            for file in files:
                file_path = os.path.join(root_dir, file)
                if is_video_file(file_path):
                    video_files.append(file_path)

        existing_files = [
            self.list_widget.item(row, 0).data(Qt.UserRole)
            for row in range(self.list_widget.rowCount())
            if self.list_widget.item(row, 0) is not None
        ]
        for file in video_files:
            if file not in existing_files:
                self.list_widget.add_file(file)
                QApplication.processEvents()

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if folder:
            self.output_folder = folder
            self.lbl_status.setText(f"Carpeta de salida: {folder}")

    def open_output_folder(self):
        if self.output_folder and os.path.isdir(self.output_folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_folder))
        else:
            QMessageBox.warning(self, "Aviso", "No se ha seleccionado una carpeta de salida")

    def add_individual_files(self):
        extensions = " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(
            self, "Agregar archivos", "", f"Video/Audio Files ({extensions})"
        )
        existing = [
            self.list_widget.item(r, 0).data(Qt.UserRole)
            for r in range(self.list_widget.rowCount())
            if self.list_widget.item(r, 0)
        ]
        for path in files:
            if is_video_file(path) and path not in existing:
                self.list_widget.add_file(path)
                existing.append(path)
                QApplication.processEvents()

    def toggle_conversion(self):
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.conversion_thread.stop()
            self.progress_bar.setValue(0)
            self.file_progress_bar.setRange(0, 100)
            self.file_progress_bar.setValue(0)
            self.btn_start.setText("Iniciar conversión")
            self.btn_start.setStyleSheet("background-color: green; color: white;")
            self.btn_input_folder.setEnabled(True)
            self.btn_output_folder.setEnabled(True)
            self.btn_add_files.setEnabled(True)
            self.dependent_quality_combo.setEnabled(True)
            self.format_combo.setEnabled(True)
            self.encoder_combo.setEnabled(True)
            self.volume_spin.setEnabled(True)
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

            files = [
                self.list_widget.item(row, 0).data(Qt.UserRole)
                for row in range(self.list_widget.rowCount())
                if self.list_widget.item(row, 0) is not None
            ]
            self.total_files = len(files)

            # Collect raw durations for indeterminate-bar detection
            self._file_durations = []
            for row in range(self.list_widget.rowCount()):
                dur_item = self.list_widget.item(row, 2)
                self._file_durations.append(
                    dur_item.data(Qt.UserRole) if dur_item else 0
                )

            # Clear error buffer for this batch
            self._error_buffer = []

            self.conversion_thread = ConversionThread(
                files,
                self.output_folder,
                self.format_combo.currentText(),
                self.dependent_quality_combo.currentText(),
                self.encoder_combo.currentText(),
                volume_boost=self.volume_spin.value(),
            )

            self.conversion_thread.file_progress_updated.connect(self.update_file_progress)
            self.conversion_thread.file_status_changed.connect(self.on_file_status_changed)
            self.conversion_thread.batch_finished.connect(self.on_batch_finished)
            self.conversion_thread.error_occurred.connect(self.accumulate_error)
            self.conversion_thread.warning_signal.connect(self.accumulate_warning)

            self.btn_start.setText("Detener conversión")
            self.btn_start.setStyleSheet("background-color: yellow; color: black;")
            self.btn_input_folder.setEnabled(False)
            self.btn_output_folder.setEnabled(False)
            self.btn_add_files.setEnabled(False)
            self.dependent_quality_combo.setEnabled(False)
            self.format_combo.setEnabled(False)
            self.encoder_combo.setEnabled(False)
            self.volume_spin.setEnabled(False)
            self.list_widget.setEnabled(False)
            self.btn_import.setEnabled(False)
            self.progress_bar.setValue(0)
            self.file_progress_bar.setRange(0, 100)
            self.file_progress_bar.setValue(0)
            self.conversion_thread.start()

    def on_file_status_changed(self, index: int, status: str):
        glyph = _STATUS_GLYPH.get(status, "")
        item = self.list_widget.item(index, 4)
        if item is not None:
            item.setText(glyph)

        if status == "converting":
            file_item = self.list_widget.item(index, 0)
            name = os.path.basename(file_item.data(Qt.UserRole)) if file_item else ""
            self.lbl_status.setText(f"Procesando: {name}")

            # Switch to indeterminate bar when duration is unknown
            duration = self._file_durations[index] if index < len(self._file_durations) else 0
            if duration == 0:
                self.file_progress_bar.setRange(0, 0)
            else:
                self.file_progress_bar.setRange(0, 100)

        elif status in ("done", "failed"):
            # Restore determinate bar on completion
            self.file_progress_bar.setRange(0, 100)
            if status == "done":
                self.file_progress_bar.setValue(100)

    def update_file_progress(self, index: int, percent: int):
        # Only update per-file bar when it is in determinate mode
        if self.file_progress_bar.maximum() > 0:
            self.file_progress_bar.setValue(percent)

        global_pct = compute_global_progress(index, percent, self.total_files)
        self.progress_bar.setValue(global_pct)

        if percent == 100:
            new_index = index + 1
            self.next_index = new_index if new_index < self.total_files else index

    def accumulate_error(self, message: str):
        self._error_buffer.append(("Error", message))

    def accumulate_warning(self, message: str):
        self._error_buffer.append(("Aviso", message))
        self.lbl_status.setText(f"Aviso: {message}")

    def on_batch_finished(self, cancelled: bool):
        self.btn_start.setText("Iniciar conversión")
        self.btn_start.setStyleSheet("background-color: green; color: white;")
        self.btn_input_folder.setEnabled(True)
        self.btn_output_folder.setEnabled(True)
        self.btn_add_files.setEnabled(True)
        self.dependent_quality_combo.setEnabled(True)
        self.format_combo.setEnabled(True)
        self.encoder_combo.setEnabled(True)
        self.volume_spin.setEnabled(True)
        self.list_widget.setEnabled(True)
        self.btn_import.setEnabled(True)
        self.file_progress_bar.setRange(0, 100)
        self.conversion_thread = None

        if cancelled:
            self.lbl_status.setText("Estado: Conversión cancelada")
            self.progress_bar.setValue(0)
            self.file_progress_bar.setValue(0)
        else:
            self.lbl_status.setText("Estado: Conversión completada")
            self.progress_bar.setValue(100)

        if self._error_buffer:
            lines = "\n".join(
                f"[{kind}] {msg}" for kind, msg in self._error_buffer
            )
            QMessageBox.warning(
                self,
                "Resumen de errores",
                f"Se produjeron {len(self._error_buffer)} avisos/errores:\n\n{lines}",
            )

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Confirmar salida",
            "¿Estás seguro de cerrar el programa?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self.conversion_thread and self.conversion_thread.isRunning():
                self.conversion_thread.stop()
            state_file = os.path.join(_get_app_data_dir(), "last_state.xml")
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
