from __future__ import annotations

import re

# Windows forbids these characters in a filename component. Control characters
# are forbidden as well. Keep canonical research/model IDs unchanged and only
# sanitize at the filesystem boundary.
_INVALID_WINDOWS_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WINDOWS_RESERVED_BASENAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
}


def filesystem_safe_id(value: object, *, fallback: str = 'artifact', max_length: int = 180) -> str:
    """Return a deterministic cross-platform-safe filename component.

    This function is intentionally applied only at filesystem boundaries.
    Canonical model/family IDs such as ``hybrid::gru::lightgbm`` must remain
    unchanged in registry, lineage, evidence, and research-plan semantics.
    """
    raw = str(value or '').strip()
    safe = _INVALID_WINDOWS_FILENAME_CHARS.sub('__', raw)
    # Windows strips/forbids trailing spaces and periods. Normalize whitespace
    # without changing the meaningful separator structure.
    safe = re.sub(r'\s+', '_', safe).strip(' .')
    safe = safe or fallback

    # Reserved DOS device names are invalid even with an extension.
    if safe.split('.', 1)[0].upper() in _WINDOWS_RESERVED_BASENAMES:
        safe = f'_{safe}'

    if len(safe) > max_length:
        safe = safe[:max_length].rstrip(' ._') or fallback
    return safe
