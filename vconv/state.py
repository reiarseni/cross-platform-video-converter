import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List

from vconv.config import VIDEO_EXTENSIONS


def _is_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


@dataclass
class AppState:
    files: List[str] = field(default_factory=list)
    output_folder: str = ""
    format_preset: str = "General PC (H.264)"
    quality: str = "Media"
    encoder: str = "Auto"
    volume_boost: int = 0
    next_index: int = 0


def to_xml(state: AppState) -> bytes:
    """Serialize AppState to XML bytes using the existing last_state.xml schema."""
    root = ET.Element("app_state")

    videos_elem = ET.SubElement(root, "videos")
    for path in state.files:
        video_elem = ET.SubElement(videos_elem, "video")
        video_elem.text = path

    ET.SubElement(root, "output_folder").text = state.output_folder or ""
    ET.SubElement(root, "quality").text = state.quality
    ET.SubElement(root, "format_preset").text = state.format_preset
    ET.SubElement(root, "encoder").text = state.encoder
    ET.SubElement(root, "volume_boost").text = str(state.volume_boost)
    ET.SubElement(root, "next_index").text = str(state.next_index)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def save(state: AppState, file_path: str) -> None:
    """Write AppState to an XML file."""
    with open(file_path, "wb") as fh:
        fh.write(to_xml(state))


def from_xml(source) -> AppState:
    """Parse AppState from a file path or XML bytes.

    Filters the file list to paths that still exist and are valid video files.
    Applies safe defaults for missing or invalid fields.
    """
    if isinstance(source, (str, os.PathLike)):
        tree = ET.parse(source)
        root = tree.getroot()
    else:
        root = ET.fromstring(source)

    state = AppState()

    videos_elem = root.find("videos")
    if videos_elem is not None:
        for video in videos_elem.findall("video"):
            path = (video.text or "").strip()
            if path and os.path.exists(path) and _is_video_file(path):
                state.files.append(path)

    out_elem = root.find("output_folder")
    if out_elem is not None and out_elem.text:
        folder = out_elem.text.strip()
        if folder and os.path.isdir(folder):
            state.output_folder = folder

    for attr, tag in [
        ("quality", "quality"),
        ("format_preset", "format_preset"),
        ("encoder", "encoder"),
    ]:
        elem = root.find(tag)
        if elem is not None and elem.text:
            setattr(state, attr, elem.text.strip())

    vol_elem = root.find("volume_boost")
    if vol_elem is not None and vol_elem.text:
        try:
            state.volume_boost = int(vol_elem.text.strip())
        except ValueError:
            pass

    idx_elem = root.find("next_index")
    if idx_elem is not None and idx_elem.text:
        try:
            state.next_index = int(idx_elem.text.strip())
        except ValueError:
            pass

    return state
