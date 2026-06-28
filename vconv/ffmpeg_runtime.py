import subprocess

from vconv.config import FFMPEG_BIN, ENCODER_AUTO, ENCODER_CPU, ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD


def _probe_encoder_works(codec: str) -> bool:
    """Return True only if the GPU encoder actually initialises (hardware present)."""
    try:
        result = subprocess.run(
            [
                FFMPEG_BIN, "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "nullsrc=s=16x16:d=0.04",
                "-vframes", "1",
                "-vcodec", codec,
                "-f", "null", "-",
            ],
            capture_output=True,
            timeout=8,
        )
        return result.returncode == 0
    except Exception:
        return False


AVAILABLE_ENCODERS = [ENCODER_AUTO, ENCODER_CPU]
_GPU_CANDIDATES = [
    (ENCODER_NVIDIA, ["h264_nvenc", "hevc_nvenc"]),
    (ENCODER_INTEL,  ["h264_qsv",   "hevc_qsv"]),
    (ENCODER_AMD,    ["h264_amf",   "hevc_amf"]),
]
for _label, _codecs in _GPU_CANDIDATES:
    if any(_probe_encoder_works(c) for c in _codecs):
        AVAILABLE_ENCODERS.append(_label)
