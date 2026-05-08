"""Parse and validate a numbered LLM response."""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple


# Matches a line beginning with [N] and captures the text until the next
# [N] marker or end-of-string. DOTALL lets a single caption's translation
# span wrapped lines; MULTILINE makes ^ match line starts.
_BLOCK_PATTERN = re.compile(
    r"^\s*\[(\d+)\]\s*(.*?)(?=^\s*\[\d+\]|\Z)",
    re.MULTILINE | re.DOTALL,
)


def parse_numbered_response(response: str) -> Dict[int, str]:
    """Parse `[N] text` blocks out of an LLM response.

    Multiple lines belonging to the same block are joined with spaces.
    Returns a mapping from the 1-based in-chunk index to the translated text.
    """
    result: Dict[int, str] = {}
    for match in _BLOCK_PATTERN.finditer(response):
        idx = int(match.group(1))
        text = match.group(2)
        # Collapse any internal whitespace/newlines that the model may
        # have introduced when wrapping.
        cleaned = " ".join(s for s in text.split() if s)
        if cleaned:
            result[idx] = cleaned
    return result


def validate_coverage(
    parsed: Dict[int, str],
    expected_count: int,
) -> Tuple[bool, List[int], List[int]]:
    """Check whether the parsed response covers all expected indices.

    Args:
        parsed: Output of `parse_numbered_response`.
        expected_count: Number of target items that were requested (1..N).

    Returns:
        (is_complete, missing_indices, unexpected_indices)
    """
    expected: Set[int] = set(range(1, expected_count + 1))
    got: Set[int] = set(parsed.keys())
    missing = sorted(expected - got)
    unexpected = sorted(got - expected)
    return (not missing and not unexpected), missing, unexpected
