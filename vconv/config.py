import os
import sys

ENCODER_AUTO = "Auto"
ENCODER_CPU = "CPU"
ENCODER_NVIDIA = "NVIDIA (NVENC)"
ENCODER_INTEL = "Intel (QSV)"
ENCODER_AMD = "AMD (AMF)"

MAX_RETRIES = 2
HANG_TIMEOUT = 60

VIDEO_EXTENSIONS = [
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".flv",
    ".wmv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".mp3",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".m4a",
    ".wma",
    ".opus",
]


def _get_app_data_dir():
    if getattr(sys, "frozen", False):
        data_dir = os.path.join(os.path.expanduser("~"), ".VideoConverter")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    # In dev mode: go up from vconv/ to the project root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_bin(name):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "bin", name)
    return name


FFMPEG_BIN = _resolve_bin("ffmpeg")
FFPROBE_BIN = _resolve_bin("ffprobe")
