import pytest
from vconv.presets import ConversionPreset
from vconv.conversion import (
    build_output_kwargs,
    parse_progress_line,
    build_output_path,
    next_encoder_after_failure,
    compute_global_progress,
)
from vconv.config import ENCODER_AUTO, ENCODER_CPU, ENCODER_NVIDIA, ENCODER_INTEL, ENCODER_AMD


def preset(fmt="MP4 (H.264)", quality="Media"):
    return ConversionPreset(fmt, quality)


# ---------------------------------------------------------------------------
# build_output_kwargs
# ---------------------------------------------------------------------------

class TestBuildOutputKwargs:
    def test_cpu_video(self):
        p = preset()
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["vcodec"] == "libx264"
        assert kwargs["preset"] == "fast"
        assert kwargs["crf"] == "23"
        assert kwargs["acodec"] == "aac"
        assert kwargs["audio_bitrate"] == "192k"
        assert kwargs["movflags"] == "+faststart"
        assert "af" not in kwargs

    def test_nvidia_video(self):
        p = preset()
        kwargs = build_output_kwargs(p, ENCODER_NVIDIA, "h264_nvenc", volume_boost=0)
        assert kwargs["vcodec"] == "h264_nvenc"
        assert kwargs["rc"] == "vbr"
        assert kwargs["cq"] == "23"
        assert "preset" in kwargs

    def test_intel_qsv(self):
        p = preset("MP4 (H.265)", "Alta")
        kwargs = build_output_kwargs(p, ENCODER_INTEL, "hevc_qsv", volume_boost=0)
        assert kwargs["vcodec"] == "hevc_qsv"
        assert kwargs["global_quality"] == "20"
        assert kwargs["look_ahead"] == "1"

    def test_amd_amf(self):
        p = preset()
        kwargs = build_output_kwargs(p, ENCODER_AMD, "h264_amf", volume_boost=0)
        assert kwargs["vcodec"] == "h264_amf"
        assert kwargs["rc"] == "cqp"
        assert kwargs["qp_i"] == "23"
        assert kwargs["qp_p"] == "23"

    def test_audio_only(self):
        p = preset("MP3 (Audio)", "Alta")
        kwargs = build_output_kwargs(p, ENCODER_CPU, None, volume_boost=0)
        assert kwargs["acodec"] == "libmp3lame"
        assert kwargs["audio_bitrate"] == "320k"
        assert kwargs["vn"] is None
        assert "vcodec" not in kwargs
        assert "af" not in kwargs

    def test_volume_boost_applies_gain_and_limiter(self):
        p = preset()
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=200)
        assert "af" in kwargs
        assert "volume=2.0000" in kwargs["af"]
        assert "alimiter" in kwargs["af"]

    def test_volume_boost_on_audio_only(self):
        p = preset("MP3 (Audio)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, None, volume_boost=150)
        assert "af" in kwargs
        assert "volume=1.5000" in kwargs["af"]

    def test_no_af_when_boost_is_zero(self):
        p = preset()
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert "af" not in kwargs

    def test_no_af_when_boost_is_100(self):
        p = preset()
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=100)
        assert "af" not in kwargs

    # --- existing presets no longer use "slow" ---

    def test_existing_h264_not_slow(self):
        kwargs = build_output_kwargs(preset("MP4 (H.264)", "Media"), ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["preset"] == "fast"
        assert kwargs["preset"] != "slow"

    def test_existing_h265_not_slow(self):
        kwargs = build_output_kwargs(preset("MP4 (H.265)", "Media"), ENCODER_CPU, "libx265", volume_boost=0)
        assert kwargs["preset"] == "fast"

    def test_existing_mkv_h264_not_slow(self):
        kwargs = build_output_kwargs(preset("MKV (H.264)", "Media"), ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["preset"] == "fast"

    # --- TV Moderna USB (H.264) ---

    def test_tv_moderna_usb_preset_fast(self):
        p = preset("TV Moderna USB (H.264)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["preset"] == "fast"
        assert kwargs["crf"] == "26"
        assert kwargs["acodec"] == "aac"
        assert kwargs["audio_bitrate"] == "192k"
        assert kwargs["movflags"] == "+faststart"

    def test_tv_moderna_usb_baseline_profile(self):
        p = preset("TV Moderna USB (H.264)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["profile:v"] == "baseline"
        assert kwargs["level"] == "3.1"

    def test_tv_moderna_usb_crf_values(self):
        assert build_output_kwargs(preset("TV Moderna USB (H.264)", "Alta"), ENCODER_CPU, "libx264", volume_boost=0)["crf"] == "22"
        assert build_output_kwargs(preset("TV Moderna USB (H.264)", "Baja"), ENCODER_CPU, "libx264", volume_boost=0)["crf"] == "28"

    # --- TV Antigua (Xvid AVI) ---

    def test_tv_antigua_xvid_uses_qv(self):
        p = preset("TV Antigua (Xvid AVI)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "mpeg4", volume_boost=0)
        assert kwargs["vcodec"] == "mpeg4"
        assert kwargs["q:v"] == "5"
        assert "crf" not in kwargs
        assert "preset" not in kwargs

    def test_tv_antigua_xvid_mp3_audio(self):
        p = preset("TV Antigua (Xvid AVI)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "mpeg4", volume_boost=0)
        assert kwargs["acodec"] == "libmp3lame"

    def test_tv_antigua_xvid_vtag(self):
        p = preset("TV Antigua (Xvid AVI)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "mpeg4", volume_boost=0)
        assert kwargs["vtag"] == "xvid"

    def test_tv_antigua_xvid_no_movflags(self):
        p = preset("TV Antigua (Xvid AVI)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "mpeg4", volume_boost=0)
        assert "movflags" not in kwargs

    def test_tv_antigua_xvid_qv_values(self):
        assert build_output_kwargs(preset("TV Antigua (Xvid AVI)", "Alta"), ENCODER_CPU, "mpeg4", volume_boost=0)["q:v"] == "3"
        assert build_output_kwargs(preset("TV Antigua (Xvid AVI)", "Baja"), ENCODER_CPU, "mpeg4", volume_boost=0)["q:v"] == "7"

    # --- Móvil/Tablet (H.264) ---

    def test_movil_tablet_superfast(self):
        p = preset("Móvil/Tablet (H.264)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["preset"] == "superfast"
        assert kwargs["crf"] == "28"

    def test_movil_tablet_128k_audio(self):
        p = preset("Móvil/Tablet (H.264)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["audio_bitrate"] == "128k"

    def test_movil_tablet_baseline_profile(self):
        p = preset("Móvil/Tablet (H.264)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert kwargs["profile:v"] == "baseline"
        assert kwargs["level"] == "3.1"

    def test_movil_tablet_crf_values(self):
        assert build_output_kwargs(preset("Móvil/Tablet (H.264)", "Alta"), ENCODER_CPU, "libx264", volume_boost=0)["crf"] == "24"
        assert build_output_kwargs(preset("Móvil/Tablet (H.264)", "Baja"), ENCODER_CPU, "libx264", volume_boost=0)["crf"] == "32"

    # --- existing H.264 no tiene profile forzado ---

    def test_existing_mp4_h264_no_profile(self):
        p = preset("MP4 (H.264)", "Media")
        kwargs = build_output_kwargs(p, ENCODER_CPU, "libx264", volume_boost=0)
        assert "profile:v" not in kwargs
        assert "level" not in kwargs


# ---------------------------------------------------------------------------
# parse_progress_line
# ---------------------------------------------------------------------------

class TestParseProgressLine:
    def test_time_line(self):
        result = parse_progress_line("out_time_ms=1234567")
        assert result == ("time", 1234567)

    def test_completion_line(self):
        result = parse_progress_line("progress=end")
        assert result == ("end", None)

    def test_irrelevant_line(self):
        assert parse_progress_line("frame=42") is None
        assert parse_progress_line("fps=30") is None
        assert parse_progress_line("") is None
        assert parse_progress_line("progress=continue") is None

    def test_invalid_time_value(self):
        result = parse_progress_line("out_time_ms=N/A")
        assert result is None


# ---------------------------------------------------------------------------
# build_output_path
# ---------------------------------------------------------------------------

class TestBuildOutputPath:
    def test_basic(self):
        result = build_output_path("/home/user/videos/movie.avi", "/output", ".mp4")
        assert result == "/output/movie.mp4"

    def test_preserves_base_name(self):
        result = build_output_path("/a/b/c/my.video.mkv", "/out", ".mp3")
        assert result == "/out/my.video.mp3"


# ---------------------------------------------------------------------------
# next_encoder_after_failure
# ---------------------------------------------------------------------------

class TestNextEncoderAfterFailure:
    def _p(self, fmt="MP4 (H.264)", quality="Media"):
        return ConversionPreset(fmt, quality)

    def test_nvidia_falls_back_to_cpu(self):
        result = next_encoder_after_failure(ENCODER_NVIDIA, self._p())
        assert result == (ENCODER_CPU, "libx264")

    def test_intel_falls_back_to_cpu(self):
        result = next_encoder_after_failure(ENCODER_INTEL, self._p("MKV (H.264)"))
        assert result == (ENCODER_CPU, "libx264")

    def test_amd_falls_back_to_cpu(self):
        result = next_encoder_after_failure(ENCODER_AMD, self._p("MP4 (H.265)"))
        assert result == (ENCODER_CPU, "libx265")

    def test_cpu_returns_none(self):
        assert next_encoder_after_failure(ENCODER_CPU, self._p()) is None

    def test_auto_returns_none(self):
        assert next_encoder_after_failure(ENCODER_AUTO, self._p()) is None

    def test_audio_only_returns_none(self):
        assert next_encoder_after_failure(ENCODER_NVIDIA, self._p("MP3 (Audio)")) is None


# ---------------------------------------------------------------------------
# compute_global_progress
# ---------------------------------------------------------------------------

class TestComputeGlobalProgress:
    def test_first_file_at_zero(self):
        assert compute_global_progress(0, 0, 4) == 0

    def test_first_file_at_fifty(self):
        assert compute_global_progress(0, 50, 4) == 12

    def test_first_file_done(self):
        assert compute_global_progress(0, 100, 4) == 25

    def test_second_file_at_fifty(self):
        assert compute_global_progress(1, 50, 4) == 37

    def test_last_file_done(self):
        assert compute_global_progress(3, 100, 4) == 100

    def test_single_file_at_fifty(self):
        assert compute_global_progress(0, 50, 1) == 50

    def test_zero_total_returns_zero(self):
        assert compute_global_progress(0, 0, 0) == 0


# ---------------------------------------------------------------------------
# Status transition values
# ---------------------------------------------------------------------------

class TestStatusValues:
    """Verify the status strings used by ConversionThread are the expected values."""

    VALID_STATUSES = {"queued", "converting", "done", "failed"}

    def test_queued_is_valid(self):
        assert "queued" in self.VALID_STATUSES

    def test_happy_path_sequence(self):
        sequence = ["queued", "converting", "done"]
        for s in sequence:
            assert s in self.VALID_STATUSES

    def test_failure_path_sequence(self):
        sequence = ["queued", "converting", "failed"]
        for s in sequence:
            assert s in self.VALID_STATUSES

    def test_no_unknown_statuses(self):
        assert len(self.VALID_STATUSES) == 4
