from vconv.config import ENCODER_AUTO, ENCODER_CPU, ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD


class ConversionPreset:
    _preset_data = {
        "MP4 (H.264)": {
            "preset_quality": {"Baja": "28", "Media": "23", "Alta": "18"},
            "container": ".mp4",
            "vcodec": "libx264",
            "ffmpeg_preset": "fast",
        },
        "MP4 (H.265)": {
            "preset_quality": {"Baja": "30", "Media": "25", "Alta": "20"},
            "container": ".mp4",
            "vcodec": "libx265",
            "ffmpeg_preset": "fast",
        },
        "AVI (MPEG-4)": {
            "preset_quality": {"Baja": "32", "Media": "27", "Alta": "22"},
            "container": ".avi",
            "vcodec": "mpeg4",
        },
        "MKV (H.264)": {
            "preset_quality": {"Baja": "28", "Media": "23", "Alta": "18"},
            "container": ".mkv",
            "vcodec": "libx264",
            "ffmpeg_preset": "fast",
        },
        "MP3 (Audio)": {
            "preset_quality": {"Baja": "128k", "Media": "192k", "Alta": "320k"},
            "container": ".mp3",
            "vcodec": None,
        },
        "TV Moderna USB (H.264)": {
            "preset_quality": {"Baja": "28", "Media": "26", "Alta": "22"},
            "container": ".mp4",
            "vcodec": "libx264",
            "ffmpeg_preset": "fast",
            "x264_profile": "baseline",
            "x264_level": "3.1",
        },
        "TV Antigua (Xvid AVI)": {
            "preset_quality": {"Baja": "7", "Media": "5", "Alta": "3"},
            "container": ".avi",
            "vcodec": "mpeg4",
            "audio_codec": "libmp3lame",
            "vtag": "xvid",
        },
        "Móvil/Tablet (H.264)": {
            "preset_quality": {"Baja": "32", "Media": "28", "Alta": "24"},
            "container": ".mp4",
            "vcodec": "libx264",
            "ffmpeg_preset": "superfast",
            "x264_profile": "baseline",
            "x264_level": "3.1",
            "audio_bitrate": "128k",
        },
    }

    _gpu_codec_map = {
        "MP4 (H.264)": {
            ENCODER_NVIDIA: "h264_nvenc",
            ENCODER_INTEL: "h264_qsv",
            ENCODER_AMD: "h264_amf",
        },
        "MP4 (H.265)": {
            ENCODER_NVIDIA: "hevc_nvenc",
            ENCODER_INTEL: "hevc_qsv",
            ENCODER_AMD: "hevc_amf",
        },
        "AVI (MPEG-4)": {},
        "MKV (H.264)": {
            ENCODER_NVIDIA: "h264_nvenc",
            ENCODER_INTEL: "h264_qsv",
            ENCODER_AMD: "h264_amf",
        },
        "MP3 (Audio)": {},
        "TV Moderna USB (H.264)": {
            ENCODER_NVIDIA: "h264_nvenc",
            ENCODER_INTEL: "h264_qsv",
            ENCODER_AMD: "h264_amf",
        },
        "TV Antigua (Xvid AVI)": {},
        "Móvil/Tablet (H.264)": {
            ENCODER_NVIDIA: "h264_nvenc",
            ENCODER_INTEL: "h264_qsv",
            ENCODER_AMD: "h264_amf",
        },
    }

    def __init__(self, format_preset: str, quality: str):
        self.format_preset = format_preset
        self.quality = quality

    @classmethod
    def get_available_presets(cls):
        return list(cls._preset_data.keys())

    @classmethod
    def get_available_qualities(cls):
        if "MP4 (H.264)" in cls._preset_data:
            return list(cls._preset_data["MP4 (H.264)"]["preset_quality"].keys())
        first_key = next(iter(cls._preset_data))
        return list(cls._preset_data[first_key]["preset_quality"].keys())

    def get_crf(self) -> str:
        return (
            self._preset_data.get(self.format_preset, {})
            .get("preset_quality", {})
            .get(self.quality, "23")
        )

    def get_container_extension(self) -> str:
        return self._preset_data.get(self.format_preset, {}).get("container", ".mp4")

    def get_video_codec(self) -> str:
        return self._preset_data.get(self.format_preset, {}).get("vcodec", "libx264")

    def is_audio_only(self) -> bool:
        return self._preset_data.get(self.format_preset, {}).get("vcodec") is None

    def get_ffmpeg_preset(self):
        return self._preset_data.get(self.format_preset, {}).get("ffmpeg_preset")

    def get_x264_profile(self):
        return self._preset_data.get(self.format_preset, {}).get("x264_profile")

    def get_x264_level(self):
        return self._preset_data.get(self.format_preset, {}).get("x264_level")

    def get_audio_bitrate(self) -> str:
        return self._preset_data.get(self.format_preset, {}).get("audio_bitrate", "192k")

    def get_audio_codec(self) -> str:
        return self._preset_data.get(self.format_preset, {}).get("audio_codec", "aac")

    def get_vtag(self):
        return self._preset_data.get(self.format_preset, {}).get("vtag")

    @classmethod
    def get_gpu_codec(cls, format_preset, encoder):
        return cls._gpu_codec_map.get(format_preset, {}).get(encoder)

    def resolve_encoder(self, preferred_encoder, available_encoders=None):
        """Returns (resolved_encoder_label, codec). Falls back to CPU when GPU unavailable.

        available_encoders: list of encoder labels to consider; defaults to runtime scan.
        """
        if available_encoders is None:
            from vconv import ffmpeg_runtime
            available_encoders = ffmpeg_runtime.AVAILABLE_ENCODERS

        if self.is_audio_only():
            return ENCODER_CPU, None

        if preferred_encoder == ENCODER_CPU:
            return ENCODER_CPU, self.get_video_codec()

        if preferred_encoder == ENCODER_AUTO:
            for label in [ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD]:
                if label in available_encoders:
                    gpu_codec = self.get_gpu_codec(self.format_preset, label)
                    if gpu_codec:
                        return label, gpu_codec
            return ENCODER_CPU, self.get_video_codec()

        gpu_codec = self.get_gpu_codec(self.format_preset, preferred_encoder)
        if gpu_codec:
            return preferred_encoder, gpu_codec
        return ENCODER_CPU, self.get_video_codec()
