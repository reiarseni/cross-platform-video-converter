import os
import queue
import threading
import time

import ffmpeg
from PyQt5.QtCore import QThread, pyqtSignal

from vconv.config import (
    ENCODER_AMD,
    ENCODER_CPU,
    ENCODER_INTEL,
    ENCODER_NVIDIA,
    FFMPEG_BIN,
    HANG_TIMEOUT,
    MAX_RETRIES,
)
from vconv.presets import ConversionPreset
from vconv.probing import get_video_duration


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def build_output_kwargs(preset: ConversionPreset, resolved_encoder: str, codec, volume_boost: int) -> dict:
    """Build ffmpeg output keyword arguments. No Qt or subprocess dependency."""
    if preset.is_audio_only():
        base = {
            "acodec": "libmp3lame",
            "audio_bitrate": preset.get_crf(),
            "vn": None,
            "progress": "pipe:1",
        }
        if volume_boost > 0 and volume_boost != 100:
            gain = volume_boost / 100.0
            base["af"] = f"volume={gain:.4f},alimiter=level_out=0.95"
        return base

    crf = preset.get_crf()
    base = {
        "acodec": preset.get_audio_codec(),
        "audio_bitrate": preset.get_audio_bitrate(),
        "progress": "pipe:1",
    }
    if preset.get_container_extension() != ".avi":
        base["movflags"] = "+faststart"

    if resolved_encoder == ENCODER_NVIDIA:
        base.update({"vcodec": codec, "preset": "p4", "rc": "vbr", "cq": crf})
    elif resolved_encoder == ENCODER_INTEL:
        base.update({"vcodec": codec, "global_quality": crf, "look_ahead": "1"})
    elif resolved_encoder == ENCODER_AMD:
        base.update({"vcodec": codec, "rc": "cqp", "qp_i": crf, "qp_p": crf})
    else:
        ffmpeg_preset = preset.get_ffmpeg_preset()
        if ffmpeg_preset is not None:
            base.update({"vcodec": codec, "preset": ffmpeg_preset, "crf": crf})
            profile = preset.get_x264_profile()
            level = preset.get_x264_level()
            if profile:
                base["profile:v"] = profile
                # Compatibility profiles (e.g. baseline) require 8-bit 4:2:0.
                # Force yuv420p so 10-bit HEVC sources don't fail encoder init
                # ("baseline profile doesn't support a bit depth of 10") and
                # so old TVs/phones can actually decode the output.
                base["pix_fmt"] = "yuv420p"
            if level:
                base["level"] = level
        else:
            # mpeg4/Xvid: no -preset support, use -q:v for quality
            base.update({"vcodec": codec, "q:v": crf})
            vtag = preset.get_vtag()
            if vtag:
                base["vtag"] = vtag

    if volume_boost > 0 and volume_boost != 100:
        gain = volume_boost / 100.0
        base["af"] = f"volume={gain:.4f},alimiter=level_out=0.95"
    return base


def parse_progress_line(line: str):
    """Parse a single FFmpeg -progress output line.

    Returns:
        ("time", microseconds_int)  for out_time_ms= lines
        ("end", None)               for progress=end
        None                        for all other lines
    """
    if line.startswith("out_time_ms="):
        try:
            return ("time", int(line.split("=", 1)[1]))
        except ValueError:
            return None
    if line.startswith("progress=") and line.split("=", 1)[1] == "end":
        return ("end", None)
    return None


def build_output_path(input_path: str, output_folder: str, container_ext: str) -> str:
    """Derive the output file path from input path, folder, and extension."""
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_folder, f"{base_name}{container_ext}")


def next_encoder_after_failure(current_encoder: str, preset: ConversionPreset):
    """Return (ENCODER_CPU, cpu_codec) when current_encoder is a GPU encoder, else None.

    Audio-only presets always return None (no GPU encoder is used for them).
    CPU is the final fallback — no further switch after it.
    """
    if current_encoder in (ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD):
        if not preset.is_audio_only():
            return (ENCODER_CPU, preset.get_video_codec())
    return None


def compute_global_progress(index: int, percent: int, total: int) -> int:
    """Compute overall batch progress from the current file index and its percent."""
    if total == 0:
        return 0
    return int(((index + percent / 100) / total) * 100)


# ---------------------------------------------------------------------------
# Qt orchestrator
# ---------------------------------------------------------------------------

class ConversionThread(QThread):
    file_progress_updated = pyqtSignal(int, int)    # (index, percent)
    file_status_changed = pyqtSignal(int, str)      # (index, status)
    batch_finished = pyqtSignal(bool)               # (cancelled)
    error_occurred = pyqtSignal(str)
    warning_signal = pyqtSignal(str)

    def __init__(
        self,
        files,
        output_folder,
        format_preset,
        quality_setting,
        encoder=ENCODER_CPU,
        volume_boost=0,
    ):
        super().__init__()
        self.files = files
        self.output_folder = output_folder
        self.conversion_preset = ConversionPreset(format_preset, quality_setting)
        self.encoder = encoder
        self.volume_boost = volume_boost
        self.running = True
        self.process = None
        self.current_output_path = None

    def _read_stdout(self, process, q):
        for line in iter(process.stdout.readline, b""):
            q.put(line)
        q.put(None)  # sentinel EOF

    def _drain_stderr(self, process):
        try:
            while process.stderr.read(4096):
                pass
        except Exception:
            pass

    def run(self):
        try:
            total_files = len(self.files)

            for i in range(total_files):
                self.file_status_changed.emit(i, "queued")

            for index, file_path in enumerate(self.files):
                if not self.running:
                    break

                container_ext = self.conversion_preset.get_container_extension()
                output_path = build_output_path(file_path, self.output_folder, container_ext)
                self.current_output_path = output_path

                self.file_status_changed.emit(index, "converting")
                self.file_progress_updated.emit(index, 0)

                duration = get_video_duration(file_path)

                resolved_encoder, vcodec = self.conversion_preset.resolve_encoder(self.encoder)
                fallback_used = False

                retry_count = 0
                file_done = False
                file_failed = False

                while not file_done and not file_failed and retry_count <= MAX_RETRIES:
                    try:
                        self.process = (
                            ffmpeg.input(file_path)
                            .output(
                                output_path,
                                **build_output_kwargs(
                                    self.conversion_preset,
                                    resolved_encoder,
                                    vcodec,
                                    self.volume_boost,
                                ),
                            )
                            .overwrite_output()
                            .run_async(cmd=FFMPEG_BIN, pipe_stdout=True, pipe_stderr=True)
                        )
                    except ffmpeg.Error as e:
                        fallback = next_encoder_after_failure(resolved_encoder, self.conversion_preset)
                        if fallback and not fallback_used:
                            fallback_used = True
                            old_encoder = resolved_encoder
                            resolved_encoder, vcodec = fallback
                            self.warning_signal.emit(
                                f"GPU encoder {old_encoder} failed for "
                                f"{os.path.basename(file_path)}, falling back to CPU"
                            )
                            retry_count += 1
                            continue
                        error_msg = e.stderr.decode() if e.stderr else str(e)
                        self.error_occurred.emit(f"Error converting {file_path}: {error_msg}")
                        file_failed = True
                        break

                    stderr_drainer = threading.Thread(
                        target=self._drain_stderr, args=(self.process,), daemon=True
                    )
                    stderr_drainer.start()

                    q = queue.Queue()
                    stdout_reader = threading.Thread(
                        target=self._read_stdout, args=(self.process, q), daemon=True
                    )
                    stdout_reader.start()

                    hung = False
                    last_progress_time = time.time()

                    while not hung and not file_done and self.running:
                        try:
                            line = q.get(timeout=1)
                            if line is None:
                                break
                            event = parse_progress_line(line.decode("utf-8").strip())
                            if event is None:
                                continue
                            if event[0] == "time":
                                out_time_ms = event[1]
                                if duration > 0:
                                    percent_file = min(
                                        100,
                                        int((out_time_ms / (duration * 1_000_000)) * 100),
                                    )
                                    self.file_progress_updated.emit(index, percent_file)
                                    last_progress_time = time.time()
                            elif event[0] == "end":
                                self.file_progress_updated.emit(index, 100)
                                file_done = True
                                break
                        except queue.Empty:
                            if time.time() - last_progress_time > HANG_TIMEOUT:
                                hung = True
                                self.warning_signal.emit(
                                    f"FFmpeg colgado - reintentando {os.path.basename(file_path)} "
                                    f"(intento {retry_count + 1}/{MAX_RETRIES})"
                                )

                    if hung:
                        try:
                            self.process.kill()
                            self.process.wait()
                            if os.path.exists(output_path):
                                os.remove(output_path)
                        except Exception:
                            pass

                        fallback = next_encoder_after_failure(resolved_encoder, self.conversion_preset)
                        if fallback and not fallback_used:
                            fallback_used = True
                            old_encoder = resolved_encoder
                            resolved_encoder, vcodec = fallback
                            self.warning_signal.emit(
                                f"GPU encoder {old_encoder} hung for "
                                f"{os.path.basename(file_path)}, falling back to CPU"
                            )

                        retry_count += 1
                        if retry_count > MAX_RETRIES:
                            self.error_occurred.emit(
                                f"Error fatal: FFmpeg se colgó en {file_path} "
                                f"después de {MAX_RETRIES} reintentos"
                            )
                            file_failed = True
                        continue
                    elif file_done:
                        retcode = self.process.wait()
                        if retcode != 0:
                            # ffmpeg emitted progress=end but exited with error
                            # (e.g. GPU encoder initialised the process but failed to encode)
                            file_done = False
                            try:
                                if os.path.exists(output_path):
                                    os.remove(output_path)
                            except Exception:
                                pass
                            fallback = next_encoder_after_failure(
                                resolved_encoder, self.conversion_preset
                            )
                            if fallback and not fallback_used:
                                fallback_used = True
                                old_encoder = resolved_encoder
                                resolved_encoder, vcodec = fallback
                                self.warning_signal.emit(
                                    f"GPU encoder {old_encoder} failed for "
                                    f"{os.path.basename(file_path)}, falling back to CPU"
                                )
                                retry_count += 1
                                continue
                            else:
                                self.error_occurred.emit(
                                    f"Error converting {file_path}: "
                                    f"FFmpeg exited with code {retcode}"
                                )
                                file_failed = True
                        break
                    elif not self.running:
                        break

                if not self.running:
                    try:
                        if os.path.exists(output_path):
                            os.remove(output_path)
                    except Exception as e:
                        self.error_occurred.emit(
                            f"Error removing incomplete file {output_path}: {str(e)}"
                        )
                    break

                if file_done:
                    self.file_status_changed.emit(index, "done")
                elif file_failed:
                    self.file_status_changed.emit(index, "failed")

            self.batch_finished.emit(not self.running)
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {str(e)}")
            self.batch_finished.emit(False)

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
        # batch_finished(True) is emitted by run() when self.running is False
