"""VTT file parsing and writing, backed by webvtt-py.

Captions are exposed as simple dataclasses with a stable 0-based `index`
so downstream code can key translation results back to their source lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import webvtt


@dataclass
class Caption:
    """A single VTT cue with its source-order index."""

    index: int        # 0-based position in the original file
    start: str        # e.g. "00:00:00.500"
    end: str          # e.g. "00:00:07.000"
    text: str         # normalized to a single line (internal newlines -> space)
    raw_text: str     # original text with newlines preserved (unused currently)


def parse_vtt(vtt_path: str | Path) -> List[Caption]:
    """Parse a VTT file into a list of Caption objects."""
    captions: List[Caption] = []
    for i, cue in enumerate(webvtt.read(str(vtt_path))):
        raw = cue.text or ""
        # Collapse multi-line caption text into a single line for translation.
        normalized = " ".join(line.strip() for line in raw.splitlines() if line.strip())
        captions.append(
            Caption(
                index=i,
                start=cue.start,
                end=cue.end,
                text=normalized,
                raw_text=raw,
            )
        )
    return captions


def write_vtt(
    output_path: str | Path,
    source_captions: List[Caption],
    translations: Dict[int, str],
) -> None:
    """Write a translated VTT file.

    Args:
        output_path: Destination file path.
        source_captions: The original parsed captions (used for timestamps).
        translations: Mapping from Caption.index to translated text. Any
            missing entry falls back to the original text.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    vtt = webvtt.WebVTT()
    for cap in source_captions:
        text = translations.get(cap.index, cap.text)
        vtt.captions.append(webvtt.Caption(cap.start, cap.end, text))

    vtt.save(str(output_path))
