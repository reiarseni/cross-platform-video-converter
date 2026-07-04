import pytest
from vconv.presets import ConversionPreset
from vconv.config import ENCODER_AUTO, ENCODER_CPU, ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD

ALL_ENCODERS = [ENCODER_AUTO, ENCODER_CPU, ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD]
NO_GPU = [ENCODER_AUTO, ENCODER_CPU]


# ---------------------------------------------------------------------------
# Preset: codec / extension / CRF
# ---------------------------------------------------------------------------

class TestPresetProperties:
    def test_mp4_h264_codec(self):
        p = ConversionPreset("General PC (H.264)", "Media")
        assert p.get_video_codec() == "libx264"
        assert p.get_container_extension() == ".mp4"
        assert p.get_crf() == "23"
        assert not p.is_audio_only()

    def test_mp4_h265_codec(self):
        p = ConversionPreset("Calidad compacta (H.265)", "Alta")
        assert p.get_video_codec() == "libx265"
        assert p.get_crf() == "20"

    def test_mkv_h264(self):
        p = ConversionPreset("Múltiples pistas (H.264)", "Media")
        assert p.get_container_extension() == ".mkv"

    def test_mp3_audio_only(self):
        p = ConversionPreset("Solo audio (MP3)", "Media")
        assert p.is_audio_only()
        assert p.get_crf() == "192k"
        assert p.get_container_extension() == ".mp3"

    def test_tv_moderna_usb_codec_and_container(self):
        p = ConversionPreset("TV Moderna USB (H.264)", "Media")
        assert p.get_video_codec() == "libx264"
        assert p.get_container_extension() == ".mp4"
        assert not p.is_audio_only()

    def test_tv_antigua_xvid_codec_and_container(self):
        p = ConversionPreset("TV Antigua (Xvid AVI)", "Media")
        assert p.get_video_codec() == "mpeg4"
        assert p.get_container_extension() == ".avi"
        assert not p.is_audio_only()

    def test_movil_tablet_codec_and_container(self):
        p = ConversionPreset("Móvil/Tablet (H.264)", "Media")
        assert p.get_video_codec() == "libx264"
        assert p.get_container_extension() == ".mp4"
        assert not p.is_audio_only()


# ---------------------------------------------------------------------------
# get_available_presets includes new presets
# ---------------------------------------------------------------------------

class TestAvailablePresets:
    def test_new_presets_in_list(self):
        presets = ConversionPreset.get_available_presets()
        assert "TV Moderna USB (H.264)" in presets
        assert "TV Antigua (Xvid AVI)" in presets
        assert "TV Express (H.264)" in presets
        assert "Móvil/Tablet (H.264)" in presets

    def test_existing_presets_still_present(self):
        presets = ConversionPreset.get_available_presets()
        assert "General PC (H.264)" in presets
        assert "Calidad compacta (H.265)" in presets
        assert "Múltiples pistas (H.264)" in presets
        assert "Solo audio (MP3)" in presets

    def test_avi_mpeg4_removed(self):
        assert "AVI (MPEG-4)" not in ConversionPreset.get_available_presets()


# ---------------------------------------------------------------------------
# get_ffmpeg_preset
# ---------------------------------------------------------------------------

class TestGetFfmpegPreset:
    def test_mp4_h264_returns_fast(self):
        assert ConversionPreset("General PC (H.264)", "Media").get_ffmpeg_preset() == "fast"

    def test_mp4_h265_returns_fast(self):
        assert ConversionPreset("Calidad compacta (H.265)", "Media").get_ffmpeg_preset() == "fast"

    def test_mkv_h264_returns_fast(self):
        assert ConversionPreset("Múltiples pistas (H.264)", "Media").get_ffmpeg_preset() == "fast"

    def test_tv_moderna_usb_returns_fast(self):
        assert ConversionPreset("TV Moderna USB (H.264)", "Media").get_ffmpeg_preset() == "fast"

    def test_movil_tablet_returns_superfast(self):
        assert ConversionPreset("Móvil/Tablet (H.264)", "Media").get_ffmpeg_preset() == "superfast"

    def test_tv_antigua_xvid_returns_none(self):
        assert ConversionPreset("TV Antigua (Xvid AVI)", "Media").get_ffmpeg_preset() is None

    def test_mp3_audio_only_returns_none(self):
        assert ConversionPreset("Solo audio (MP3)", "Media").get_ffmpeg_preset() is None


# ---------------------------------------------------------------------------
# get_x264_profile / get_x264_level
# ---------------------------------------------------------------------------

class TestX264Profile:
    def test_tv_moderna_usb_baseline_31(self):
        p = ConversionPreset("TV Moderna USB (H.264)", "Media")
        assert p.get_x264_profile() == "baseline"
        assert p.get_x264_level() == "3.1"

    def test_movil_tablet_baseline_31(self):
        p = ConversionPreset("Móvil/Tablet (H.264)", "Media")
        assert p.get_x264_profile() == "baseline"
        assert p.get_x264_level() == "3.1"

    def test_mp4_h264_no_profile(self):
        p = ConversionPreset("General PC (H.264)", "Media")
        assert p.get_x264_profile() is None
        assert p.get_x264_level() is None

    def test_mkv_h264_no_profile(self):
        p = ConversionPreset("Múltiples pistas (H.264)", "Media")
        assert p.get_x264_profile() is None


# ---------------------------------------------------------------------------
# get_audio_bitrate
# ---------------------------------------------------------------------------

class TestGetAudioBitrate:
    def test_movil_tablet_128k(self):
        assert ConversionPreset("Móvil/Tablet (H.264)", "Media").get_audio_bitrate() == "128k"

    def test_tv_moderna_usb_default_192k(self):
        assert ConversionPreset("TV Moderna USB (H.264)", "Media").get_audio_bitrate() == "192k"

    def test_mp4_h264_default_192k(self):
        assert ConversionPreset("General PC (H.264)", "Media").get_audio_bitrate() == "192k"

    def test_tv_antigua_default_192k(self):
        assert ConversionPreset("TV Antigua (Xvid AVI)", "Media").get_audio_bitrate() == "192k"


# ---------------------------------------------------------------------------
# get_audio_codec
# ---------------------------------------------------------------------------

class TestGetAudioCodec:
    def test_tv_antigua_libmp3lame(self):
        assert ConversionPreset("TV Antigua (Xvid AVI)", "Media").get_audio_codec() == "libmp3lame"

    def test_mp4_h264_aac(self):
        assert ConversionPreset("General PC (H.264)", "Media").get_audio_codec() == "aac"

    def test_tv_moderna_usb_aac(self):
        assert ConversionPreset("TV Moderna USB (H.264)", "Media").get_audio_codec() == "aac"

    def test_movil_tablet_aac(self):
        assert ConversionPreset("Móvil/Tablet (H.264)", "Media").get_audio_codec() == "aac"


# ---------------------------------------------------------------------------
# resolve_encoder
# ---------------------------------------------------------------------------

class TestResolveEncoder:
    def test_cpu_encoder(self):
        p = ConversionPreset("General PC (H.264)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_CPU, available_encoders=ALL_ENCODERS)
        assert enc == ENCODER_CPU
        assert codec == "libx264"

    def test_auto_picks_nvidia_when_available(self):
        p = ConversionPreset("General PC (H.264)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_AUTO, available_encoders=[ENCODER_AUTO, ENCODER_CPU, ENCODER_NVIDIA])
        assert enc == ENCODER_NVIDIA
        assert codec == "h264_nvenc"

    def test_auto_falls_back_to_cpu_when_no_gpu(self):
        p = ConversionPreset("General PC (H.264)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_AUTO, available_encoders=NO_GPU)
        assert enc == ENCODER_CPU
        assert codec == "libx264"

    def test_specific_gpu_unsupported_by_preset_falls_back_to_cpu(self):
        p = ConversionPreset("TV Antigua (Xvid AVI)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_NVIDIA, available_encoders=ALL_ENCODERS)
        assert enc == ENCODER_CPU
        assert codec == "mpeg4"

    def test_audio_only_ignores_gpu(self):
        p = ConversionPreset("Solo audio (MP3)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_NVIDIA, available_encoders=ALL_ENCODERS)
        assert enc == ENCODER_CPU
        assert codec is None

    def test_auto_tries_intel_when_only_intel_available(self):
        p = ConversionPreset("Calidad compacta (H.265)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_AUTO, available_encoders=[ENCODER_AUTO, ENCODER_CPU, ENCODER_INTEL])
        assert enc == ENCODER_INTEL
        assert codec == "hevc_qsv"

    def test_specific_amd_encoder(self):
        p = ConversionPreset("Múltiples pistas (H.264)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_AMD, available_encoders=ALL_ENCODERS)
        assert enc == ENCODER_AMD
        assert codec == "h264_amf"

    def test_tv_moderna_usb_nvidia_resolves_h264_nvenc(self):
        p = ConversionPreset("TV Moderna USB (H.264)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_NVIDIA, available_encoders=ALL_ENCODERS)
        assert enc == ENCODER_NVIDIA
        assert codec == "h264_nvenc"

    def test_movil_tablet_intel_resolves_h264_qsv(self):
        p = ConversionPreset("Móvil/Tablet (H.264)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_INTEL, available_encoders=ALL_ENCODERS)
        assert enc == ENCODER_INTEL
        assert codec == "h264_qsv"

    def test_tv_antigua_xvid_no_gpu_falls_back_to_cpu(self):
        p = ConversionPreset("TV Antigua (Xvid AVI)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_NVIDIA, available_encoders=ALL_ENCODERS)
        assert enc == ENCODER_CPU
        assert codec == "mpeg4"

    def test_tv_moderna_usb_auto_picks_amd(self):
        p = ConversionPreset("TV Moderna USB (H.264)", "Media")
        enc, codec = p.resolve_encoder(ENCODER_AUTO, available_encoders=[ENCODER_AUTO, ENCODER_CPU, ENCODER_AMD])
        assert enc == ENCODER_AMD
        assert codec == "h264_amf"
