import os
import tempfile
import pytest

from vconv.state import AppState, to_xml, from_xml, save


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_round_trip_preserves_all_fields(self, tmp_path):
        original = AppState(
            files=["/fake/path/a.mp4", "/fake/path/b.mkv"],
            output_folder=str(tmp_path),
            format_preset="MKV (H.264)",
            quality="Alta",
            encoder="NVIDIA (NVENC)",
            volume_boost=200,
            next_index=3,
        )
        xml_bytes = to_xml(original)
        # Files that don't exist are dropped by from_xml; we test the rest
        restored = from_xml(xml_bytes)
        assert restored.output_folder == str(tmp_path)
        assert restored.format_preset == "MKV (H.264)"
        assert restored.quality == "Alta"
        assert restored.encoder == "NVIDIA (NVENC)"
        assert restored.volume_boost == 200
        assert restored.next_index == 3

    def test_round_trip_with_real_files(self, tmp_path):
        # Create a fake .mp4 so it passes the existence + extension check
        fake_video = tmp_path / "clip.mp4"
        fake_video.write_bytes(b"fake")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        original = AppState(
            files=[str(fake_video)],
            output_folder=str(out_dir),
            format_preset="MP4 (H.264)",
            quality="Media",
            encoder="Auto",
            volume_boost=0,
            next_index=0,
        )
        xml_bytes = to_xml(original)
        restored = from_xml(xml_bytes)
        assert restored.files == [str(fake_video)]
        assert restored.output_folder == str(out_dir)

    def test_save_and_load_file(self, tmp_path):
        state_file = tmp_path / "state.xml"
        video = tmp_path / "video.mkv"
        video.write_bytes(b"x")
        original = AppState(files=[str(video)], output_folder=str(tmp_path))
        save(original, str(state_file))
        assert state_file.exists()
        restored = from_xml(str(state_file))
        assert restored.files == [str(video)]


# ---------------------------------------------------------------------------
# Stale-path filtering
# ---------------------------------------------------------------------------

class TestStalePathFiltering:
    def test_nonexistent_paths_are_dropped(self, tmp_path):
        state = AppState(files=["/nonexistent/video.mp4"])
        xml_bytes = to_xml(state)
        restored = from_xml(xml_bytes)
        assert restored.files == []

    def test_non_video_extensions_are_dropped(self, tmp_path):
        doc = tmp_path / "document.txt"
        doc.write_bytes(b"text")
        state = AppState(files=[str(doc)])
        xml_bytes = to_xml(state)
        restored = from_xml(xml_bytes)
        assert restored.files == []

    def test_valid_file_is_kept(self, tmp_path):
        vid = tmp_path / "movie.mp4"
        vid.write_bytes(b"data")
        state = AppState(files=[str(vid)])
        xml_bytes = to_xml(state)
        restored = from_xml(xml_bytes)
        assert restored.files == [str(vid)]


# ---------------------------------------------------------------------------
# Missing / invalid field defaults
# ---------------------------------------------------------------------------

MINIMAL_XML = b"<?xml version='1.0' encoding='utf-8'?><app_state></app_state>"

class TestMissingFieldDefaults:
    def test_all_defaults_on_empty_xml(self):
        state = from_xml(MINIMAL_XML)
        assert state.files == []
        assert state.output_folder == ""
        assert state.format_preset == "MP4 (H.264)"
        assert state.quality == "Media"
        assert state.encoder == "Auto"
        assert state.volume_boost == 0
        assert state.next_index == 0

    def test_invalid_next_index_defaults_to_zero(self):
        xml = b"""<?xml version='1.0' encoding='utf-8'?>
<app_state>
  <next_index>abc</next_index>
  <volume_boost>xyz</volume_boost>
</app_state>"""
        state = from_xml(xml)
        assert state.next_index == 0
        assert state.volume_boost == 0


# ---------------------------------------------------------------------------
# Golden-file compatibility: parse legacy_state.xml
# ---------------------------------------------------------------------------

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestGoldenFile:
    def test_parse_legacy_state(self, tmp_path):
        # The legacy fixture has one existing (/tmp/existing_video.mp4) and one
        # nonexistent path. We create the existing one so the filter keeps it.
        existing = "/tmp/existing_video.mp4"
        try:
            with open(existing, "wb") as fh:
                fh.write(b"fake")
            state = from_xml(os.path.join(FIXTURE_DIR, "legacy_state.xml"))
            assert existing in state.files
            assert "/tmp/nonexistent_video.mp4" not in state.files
            assert state.output_folder == "/tmp"
            assert state.quality == "Baja"
            assert state.format_preset == "MP4 (H.264)"
            assert state.encoder == "Auto"
            assert state.volume_boost == 150
            assert state.next_index == 1
        finally:
            if os.path.exists(existing):
                os.remove(existing)
