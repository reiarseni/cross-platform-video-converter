# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (requires FFmpeg in PATH or ffmpeg_bins/)
python main.py

# Run tests
python -m pytest

# Build distributable (downloads FFmpeg, compiles with PyInstaller)
./build.sh
```

## Architecture

PyQt5 desktop application for batch video conversion using FFmpeg. The non-UI logic lives in the `vconv/` package; `main.py` is the thin Qt shell.

### Package layout

```
main.py              — Qt shell: MainWindow, DragDropTableWidget, entrypoint
vconv/
  config.py          — Constants (FFMPEG_BIN, ENCODER_*, HANG_TIMEOUT, …) and bin/data-dir resolution. No imports from other vconv modules.
  presets.py         — ConversionPreset: codec/container/CRF/encoder logic
  ffmpeg_runtime.py  — Encoder availability scan (AVAILABLE_ENCODERS)
  probing.py         — ffprobe helpers (codec, duration) and formatters
  conversion.py      — Pure helpers (build_output_kwargs, parse_progress_line, build_output_path) + ConversionThread(QThread)
  state.py           — AppState dataclass, to_xml / from_xml / save (no Qt dependency)
tests/
  test_presets.py
  test_conversion.py
  test_state.py
```

### Class Overview

- **`ConversionPreset`** (`vconv/presets.py`) — Centralized registry for output format presets. Maps preset names to codec, container extension, and CRF quality values. `resolve_encoder()` accepts an `available_encoders` list as a parameter (defaults to runtime scan) for testability.

- **`DragDropTableWidget`** (`main.py`) — Custom `QTableWidget` that accepts drag-and-drop video files. Calls `vconv.probing` on drop to populate codec, duration, and size metadata.

- **`ConversionThread(QThread)`** (`vconv/conversion.py`) — Runs FFmpeg conversion off the main thread. Delegates to pure helpers (`build_output_kwargs`, `parse_progress_line`). Supports cancellation.

- **`MainWindow(QMainWindow)`** (`main.py`) — Application shell. Wires together the table, controls, and `ConversionThread`. Uses `_state_from_widgets()` / `_apply_state_to_widgets()` mappers plus `vconv.state` for save/restore.

### Signal/Data Flow

1. User drops files → `DragDropTableWidget` probes metadata via `vconv.probing` → rows added to table
2. User picks output folder, format preset, quality → stored in `MainWindow`
3. Start conversion → `MainWindow` spawns `ConversionThread` with current settings
4. `ConversionThread` emits `progress_updated` / `file_progress_updated` / `error_occurred` / `warning_signal` → `MainWindow` updates UI
5. On exit, `MainWindow.closeEvent` calls `_state_from_widgets()` and `vconv.state.save()` → `last_state.xml`

### Format Presets

Defined entirely in `ConversionPreset._preset_data`. Adding a new output format requires updating:
- `_preset_data` dict (codec, container extension, quality levels) — optional fields: `ffmpeg_preset` (libx264/libx265 speed preset), `x264_profile` / `x264_level` (e.g. `"baseline"` / `"3.1"`), `audio_codec` (default `"aac"`), `audio_bitrate` (default `"192k"`), `vtag` (e.g. `"xvid"`)
- `_gpu_codec_map` dict (GPU encoder equivalents per preset)

Presets without `ffmpeg_preset` (e.g. mpeg4/Xvid) use `-q:v` instead of `-crf` in `build_output_kwargs`.

### State Persistence

`last_state.xml` is auto-generated at runtime (gitignored). Schema is owned by `vconv/state.py`. `AppState` is a plain dataclass with no Qt dependency, making it unit-testable.
