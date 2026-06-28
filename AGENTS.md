# AGENTS.md - Agent Guidelines for Video Converter

## Project Overview

PyQt5 desktop application for batch video conversion using FFmpeg. Non-UI logic is in the `vconv/` package; `main.py` is the thin Qt shell (~250 lines).

- **Language**: Python 3
- **GUI Framework**: PyQt5
- **Core Dependencies**: PyQt5>=5.15.0, ffmpeg-python>=0.2.0, pytest>=7.0
- **Runtime Requirement**: FFmpeg must be installed and in PATH

---

## Commands

### Installation
```bash
pip install -r requirements.txt
```

### Running the Application
```bash
python main.py
```

### Testing
```bash
python -m pytest
```

### Linting/Type Checking
No linter or type checker is configured.

---

## Code Style Guidelines

### General Principles
- Non-UI logic belongs in `vconv/`. Keep `main.py` as a thin Qt shell.
- Follow the existing code style and patterns.
- No comments unless the WHY is non-obvious.
- Keep functions focused and small (single responsibility).

### Naming Conventions
| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `ConversionPreset`, `DragDropTableWidget` |
| Functions/variables | snake_case | `is_video_file`, `get_video_codec` |
| Constants (module-level) | UPPER_SNAKE_CASE | `ENCODER_CPU`, `VIDEO_EXTENSIONS` |
| Qt signals/attributes | snake_case with descriptive names | `progress_updated`, `error_occurred` |

### Package Structure
```
main.py                — Qt shell: MainWindow, DragDropTableWidget, entrypoint
vconv/
  config.py            — Constants and bin/data-dir helpers (no intra-package imports)
  presets.py           — ConversionPreset (codec/container/CRF/encoder resolution)
  ffmpeg_runtime.py    — Encoder availability scan
  probing.py           — ffprobe helpers and formatters (no Qt)
  conversion.py        — Pure helpers + ConversionThread(QThread)
  state.py             — AppState dataclass, to_xml / from_xml / save (no Qt)
tests/
  test_presets.py
  test_conversion.py
  test_state.py
  fixtures/
    legacy_state.xml   — Golden-file XML for schema compatibility tests
```

### Import Guidelines
- Group imports by category (stdlib, PyQt5, vconv, third-party)
- Use explicit imports from PyQt5: `from PyQt5.QtWidgets import (...)`
- Avoid wildcard imports (`from X import *`)
- `vconv.config` must not import from other `vconv` modules (no cycles)

### Type Hints
- Add type hints to public functions and class methods
- Use Python built-in types: `str`, `int`, `bool`, `list`, `dict`
- For complex types, use `typing` module (e.g., `List[str]`, `Optional[int]`)

### PyQt5 Patterns
- Use `pyqtSignal` for thread communication (defined at class level)
- Use `QThread` for long-running operations (`ConversionThread`)
- Always use `super().__init__(parent)` for Qt widgets
- Connect signals using `.connect()` method
- Use `Qt.UserRole` for storing custom data in model items
- Enable event processing in loops: `QApplication.processEvents()`

### Error Handling
- Use try/except blocks with specific exception types where possible
- For FFmpeg errors, catch `ffmpeg.Error` and access `e.stderr`
- For file operations, catch `OSError` or `FileNotFoundError`
- Always return sensible defaults on error (e.g., `"Unknown"`, `0`, `""`)
- Log meaningful error messages via `QMessageBox.critical()` for user-facing errors

### Thread Safety
- All FFmpeg conversion runs in `ConversionThread` (QThread subclass in `vconv/conversion.py`)
- Never block the main Qt event loop
- Use signals to update UI from worker threads
- Implement cancellation via shared `running` flag
- Clean up incomplete files on stop

### UI State Persistence
- `AppState` dataclass in `vconv/state.py` owns the schema (no Qt dependency)
- `MainWindow` maps widgets ↔ `AppState` via `_state_from_widgets()` / `_apply_state_to_widgets()`
- Use `vconv.state.save()` / `vconv.state.from_xml()` for all read/write
- Do NOT commit `last_state.xml` — it is gitignored

### Preset System
- All format/quality logic centralized in `ConversionPreset` in `vconv/presets.py`
- `_preset_data` dict maps format name to container, codec, CRF values
- `_gpu_codec_map` dict provides GPU encoder equivalents
- `resolve_encoder(preferred, available_encoders=None)` accepts the encoder list as a parameter (defaults to runtime scan) — pass a controlled list in tests
- To add a new preset: update both `_preset_data` and `_gpu_codec_map`

### GUI Labels
- Currently uses Spanish labels. Maintain this for consistency with existing UI.

---

## Architecture Summary

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `vconv/config.py` | Constants, bin resolution, app-data dir (no intra-package imports) |
| `vconv/presets.py` | ConversionPreset: codec/container/CRF/encoder resolution |
| `vconv/ffmpeg_runtime.py` | Encoder availability scan at startup |
| `vconv/probing.py` | ffprobe helpers and size/duration formatters |
| `vconv/conversion.py` | Pure FFmpeg arg builders + ConversionThread |
| `vconv/state.py` | AppState dataclass + XML serializer/parser |
| `main.py` | DragDropTableWidget, MainWindow, entrypoint |

### Signal Flow
```
User drops files → DragDropTableWidget → vconv.probing → rows added
User picks folder/format/quality → stored in MainWindow
Start conversion → MainWindow spawns ConversionThread (vconv.conversion)
ConversionThread emits progress/finished/error signals → MainWindow updates UI
On exit → _state_from_widgets() + vconv.state.save() → last_state.xml
```

### Key Files
| File | Purpose |
|------|---------|
| `main.py` | Qt shell (~250 lines) |
| `vconv/` | Non-UI logic package |
| `tests/` | pytest suite |
| `requirements.txt` | Python dependencies |
| `last_state.xml` | Auto-generated state file (gitignored) |

---

## What NOT To Do

- Do NOT add any logging framework (no loguru, logging module, etc.)
- Do NOT add type checking/linting tools
- Do NOT add CI/CD configuration
- Do NOT commit `last_state.xml` — it is gitignored
- Do NOT introduce new dependencies without explicit user request
- Do NOT put Qt imports in `vconv/state.py`, `vconv/presets.py`, `vconv/probing.py`, or `vconv/config.py`
- Do NOT import from other `vconv` modules inside `vconv/config.py`
