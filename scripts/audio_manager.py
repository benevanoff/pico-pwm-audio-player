#!/usr/bin/env python3
"""Qt desktop manager for listing and uploading Pico audio slots."""

import sys
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from audio_reader import read_audio

try:
    import serial
    from serial.tools import list_ports
except ImportError as error:
    raise SystemExit("This tool requires pyserial: python3 -m pip install pyserial") from error

try:
    from PySide6.QtCore import QObject, QThread, Signal, Slot
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
except ImportError as error:
    raise SystemExit("This tool requires PySide6: python3 -m pip install PySide6") from error


HEADER = struct.Struct("<4sIII")
MAX_SAMPLES = (1800 * 1024) - 4096
FLASH_PAGE_SIZE = 256
AUDIO_DIRECTORY_SIZE = 4096
RASPBERRY_PI_USB_VENDOR_ID = 0x2E8A


def is_pico_port(port_info) -> bool:
    """Identify Pico CDC ports using USB metadata when available."""
    if port_info.vid == RASPBERRY_PI_USB_VENDOR_ID:
        return True
    metadata = " ".join(
        value or ""
        for value in (port_info.description, port_info.manufacturer, port_info.product)
    ).lower()
    return "pico" in metadata or "rp2040" in metadata or "rp2350" in metadata


def format_duration(samples: int, sample_rate: int) -> str:
    total_seconds = samples // sample_rate
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


@dataclass
class AudioClip:
    file_id: int
    samples: int
    sample_rate: int
    storage_bytes: int


@dataclass
class FlashStats:
    program_size: int
    audio_used: int
    audio_payload: int
    audio_free: int
    audio_capacity: int


def checksum(data: bytes) -> int:
    value = 0xFFFFFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 & -(value & 1))
    return value


class PicoProtocol:
    def __init__(self, port: str, baud_rate: int, log):
        self.port = port
        self.baud_rate = baud_rate
        self.log = log
        self.supports_storage_stats = False

    def _wait_for_ready(self, serial_port) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            line = serial_port.readline().decode("ascii", errors="replace").strip()
            if line:
                self.log(f"Pico: {line}")
            if line == "READY":
                return
        raise TimeoutError("Timed out waiting for READY from the Pico")

    def _open(self):
        return serial.Serial(self.port, self.baud_rate, timeout=0.25, write_timeout=10)

    def list_audio(self) -> List[AudioClip]:
        clips: List[AudioClip] = []
        with self._open() as serial_port:
            self._wait_for_ready(serial_port)
            serial_port.write(b"L")
            serial_port.flush()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                line = serial_port.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue
                self.log(f"Pico: {line}")
                if line.startswith("AUDIO "):
                    fields = line.split()
                    if len(fields) not in (6, 8) or fields[2] != "SIZE" or fields[4] != "RATE":
                        raise RuntimeError(f"Unexpected response: {line}")
                    samples = int(fields[3])
                    storage_bytes = (
                        int(fields[7]) if len(fields) == 8 and fields[6] == "STORAGE"
                        else (samples + FLASH_PAGE_SIZE - 1) // FLASH_PAGE_SIZE * FLASH_PAGE_SIZE
                    )
                    self.supports_storage_stats |= len(fields) == 8 and fields[6] == "STORAGE"
                    clips.append(AudioClip(
                        int(fields[1]), samples, int(fields[5]), storage_bytes
                    ))
                elif line.startswith("AUDIO_LIST "):
                    return clips
        raise TimeoutError("Timed out waiting for flash listing")

    def flash_stats(self) -> FlashStats:
        with self._open() as serial_port:
            self._wait_for_ready(serial_port)
            serial_port.write(b"S")
            serial_port.flush()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                line = serial_port.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue
                self.log(f"Pico: {line}")
                if line.startswith("FLASH_STATS "):
                    fields = line.split()
                    if len(fields) != 6:
                        raise RuntimeError(f"Unexpected response: {line}")
                    return FlashStats(*(int(field) for field in fields[1:]))
        raise TimeoutError("Timed out waiting for flash statistics")

    def upload(self, file_id: int, path: str, progress=None) -> None:
        sample_rate, samples = read_audio(path)
        if progress is not None:
            progress(0, len(samples))
        with self._open() as serial_port:
            self._wait_for_ready(serial_port)
            serial_port.write(bytes((file_id,)))
            serial_port.write(HEADER.pack(b"AUD1", sample_rate, len(samples), checksum(samples)))
            for offset in range(0, len(samples), 256):
                chunk = samples[offset:offset + 256]
                serial_port.write(chunk)
                if progress is not None:
                    progress(min(offset + len(chunk), len(samples)), len(samples))
            serial_port.flush()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                line = serial_port.readline().decode("ascii", errors="replace").strip()
                if line:
                    self.log(f"Pico: {line}")
                if line == "UPLOAD_OK":
                    return
                if line.startswith("UPLOAD_ERR"):
                    raise RuntimeError(line)
        raise TimeoutError("Timed out waiting for upload result")


class SerialWorker(QObject):
    listed = Signal(object)
    stats_ready = Signal(object)
    completed = Signal()
    failed = Signal(str)
    log = Signal(str)
    progress = Signal(int)

    def __init__(self, port: str, baud_rate: int, files: Optional[List[tuple[int, str]]] = None):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self.files = files

    @Slot()
    def run(self) -> None:
        try:
            protocol = PicoProtocol(self.port, self.baud_rate, self.log.emit)
            if self.files is None:
                clips = protocol.list_audio()
                self.listed.emit(clips)
                if protocol.supports_storage_stats:
                    self.stats_ready.emit(protocol.flash_stats())
            else:
                for file_id, path in self.files:
                    self.log.emit(f"Uploading {Path(path).name} to slot {file_id}...")
                    protocol.upload(
                        file_id,
                        path,
                        lambda sent, total: self.progress.emit(
                            int(sent * 100 / total)
                        ),
                    )
                    self.log.emit(f"Uploaded {Path(path).name} to slot {file_id}")
            self.completed.emit()
        except (OSError, ValueError, TimeoutError, RuntimeError) as error:
            self.failed.emit(str(error))


class AudioManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pico Audio Manager")
        self.resize(760, 540)
        self.thread: Optional[QThread] = None
        self.worker: Optional[SerialWorker] = None
        self._build_ui()
        self.refresh_ports()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        connection = QGroupBox("Connection")
        form = QFormLayout(connection)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(300)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_ports)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(refresh_button)
        form.addRow("Serial device", port_row)
        layout.addWidget(connection)

        advanced = QGroupBox("Advanced")
        advanced_form = QFormLayout(advanced)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "57600", "115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")
        advanced_form.addRow("Baud rate", self.baud_combo)
        layout.addWidget(advanced)

        self.refresh_button = QPushButton("Refresh audio list")
        self.refresh_button.clicked.connect(self.refresh_audio)
        layout.addWidget(self.refresh_button)

        self.audio_list = QListWidget()
        self.audio_list.setAlternatingRowColors(True)
        layout.addWidget(self.audio_list, 1)
        self.storage_label = QLabel("Storage: not queried")
        layout.addWidget(self.storage_label)

        upload_box = QGroupBox("Add audio files")
        upload_layout = QFormLayout(upload_box)
        self.index_spin = QSpinBox()
        self.index_spin.setRange(1, 255)
        self.index_spin.setValue(1)
        self.index_spin.setToolTip("The first 1-based Pico audio slot to write")
        upload_layout.addRow("Start slot", self.index_spin)
        self.files_label = QLabel("No audio files selected")
        choose_button = QPushButton("Choose audio files...")
        choose_button.clicked.connect(self.choose_files)
        files_row = QHBoxLayout()
        files_row.addWidget(self.files_label, 1)
        files_row.addWidget(choose_button)
        upload_layout.addRow("Files", files_row)
        self.upload_button = QPushButton("Upload to selected slots")
        self.upload_button.clicked.connect(self.upload_files)
        upload_layout.addRow("", self.upload_button)
        self.upload_progress = QProgressBar()
        self.upload_progress.setRange(0, 100)
        self.upload_progress.setValue(0)
        self.upload_progress.setTextVisible(True)
        upload_layout.addRow("Upload progress", self.upload_progress)
        layout.addWidget(upload_box)

        self.status_label = QLabel("Select a serial device, then refresh the audio list.")
        layout.addWidget(self.status_label)
        self.setCentralWidget(root)
        self.selected_files: List[str] = []

    def refresh_ports(self) -> None:
        current = self.port_combo.currentData()
        self.port_combo.clear()
        ports = list(list_ports.comports())
        pico_ports = [port for port in ports if is_pico_port(port)]
        for port in ports:
            label = f"{port.device} - {port.description}"
            if is_pico_port(port):
                label += " (Raspberry Pi Pico)"
            self.port_combo.addItem(label, port.device)
        if current:
            index = self.port_combo.findData(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        elif pico_ports:
            self.port_combo.setCurrentIndex(self.port_combo.findData(pico_ports[0].device))
        if self.port_combo.count() == 0:
            self.port_combo.addItem("No serial devices found", "")

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Choose mono WAV or MP3 files", "", "Audio files (*.wav *.mp3)"
        )
        if files:
            self.selected_files = files
            self.files_label.setText(f"{len(files)} file(s) selected")

    def selected_connection(self) -> Optional[tuple[str, int]]:
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No serial device", "Choose an available /dev/tty device first.")
            return None
        return str(port), int(self.baud_combo.currentText())

    def start_worker(self, files: Optional[List[tuple[int, str]]] = None) -> None:
        connection = self.selected_connection()
        if connection is None:
            return
        port, baud_rate = connection
        self.set_busy(True)
        self.thread = QThread(self)
        self.worker = SerialWorker(port, baud_rate, files)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.listed.connect(self.show_audio)
        self.worker.stats_ready.connect(self.show_stats)
        self.worker.log.connect(self.status_label.setText)
        self.worker.progress.connect(self.upload_progress.setValue)
        self.worker.failed.connect(self.operation_failed)
        self.worker.completed.connect(self.operation_finished)
        self.worker.completed.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker_finished)
        self.thread.start()

    def refresh_audio(self) -> None:
        self.start_worker()

    def show_audio(self, clips: List[AudioClip]) -> None:
        self.audio_list.clear()
        for clip in clips:
            storage_kb = clip.storage_bytes / 1024
            item = QListWidgetItem(
                f"Slot {clip.file_id:3d}    {clip.samples:,} samples    "
                f"{clip.sample_rate:,} Hz    {format_duration(clip.samples, clip.sample_rate)}    "
                f"{storage_kb:.2f} KB"
            )
            item.setData(256, clip.file_id)
            self.audio_list.addItem(item)
        self.status_label.setText(f"{len(clips)} audio file(s) found")

    def show_stats(self, stats: FlashStats) -> None:
        def kb(value: int) -> str:
            return f"{value / 1024:.2f} KB"

        self.storage_label.setText(
            "Storage: "
            f"program {kb(stats.program_size)} | "
            f"audio region {kb(stats.audio_capacity)} | "
            f"directory {kb(AUDIO_DIRECTORY_SIZE)} | "
            f"audio allocated {kb(stats.audio_used)} | "
            f"audio payload {kb(stats.audio_payload)} | "
            f"free audio {kb(stats.audio_free)}"
        )

    def upload_files(self) -> None:
        if not self.selected_files:
            QMessageBox.warning(self, "No audio files", "Choose one or more WAV or MP3 files to upload.")
            return
        start = self.index_spin.value()
        if start + len(self.selected_files) - 1 > 255:
            QMessageBox.warning(self, "Slot range", "The selected files would exceed slot 255.")
            return
        files = [(start + offset, path) for offset, path in enumerate(self.selected_files)]
        self.upload_progress.setValue(0)
        self.start_worker(files)

    def set_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)
        self.upload_button.setEnabled(not busy)
        self.port_combo.setEnabled(not busy)
        self.baud_combo.setEnabled(not busy)
        self.status_label.setText("Communicating with Pico..." if busy else self.status_label.text())

    @Slot(str)
    def operation_failed(self, message: str) -> None:
        self.status_label.setText(f"Error: {message}")
        QMessageBox.critical(self, "Pico operation failed", message)

    @Slot()
    def operation_finished(self) -> None:
        self.status_label.setText("Operation complete")

    @Slot()
    def worker_finished(self) -> None:
        refresh_after_upload = self.worker is not None and self.worker.files is not None
        self.thread = None
        self.worker = None
        self.set_busy(False)
        if refresh_after_upload:
            self.refresh_audio()


def main() -> int:
    app = QApplication(sys.argv)
    window = AudioManager()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
