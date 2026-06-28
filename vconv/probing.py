import os

import ffmpeg

from vconv.config import FFPROBE_BIN, VIDEO_EXTENSIONS


def is_video_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_EXTENSIONS


def get_video_codec(file_path):
    try:
        probe = ffmpeg.probe(file_path, cmd=FFPROBE_BIN)
        video_streams = [s for s in probe["streams"] if s.get("codec_type") == "video"]
        if video_streams:
            return video_streams[0].get("codec_name", "Unknown")
        return "Unknown"
    except Exception:
        return "Unknown"


def get_video_duration(file_path):
    try:
        probe = ffmpeg.probe(file_path, cmd=FFPROBE_BIN)
        duration = float(probe.get("format", {}).get("duration", 0))
        return duration
    except Exception:
        return 0


def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    return f"{bytes_size / (1024 * 1024):.2f} MB"
