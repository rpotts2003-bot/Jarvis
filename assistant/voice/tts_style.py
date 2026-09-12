"""Free Windows British-male TTS style (Jarvis manner — not a celebrity clone)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TtsStyle:
    # pyttsx3 rate ~200 default; lower = more measured (Jarvis never rushes)
    rate: int = 145
    # pyttsx3 volume 0.0–1.0
    volume: float = 0.92
    # Soft preference string matched against voice name/id (optional override)
    voice_hint: str = "George"


# Scoring keywords for SAPI / OneCore voice ids on Windows
_UK_HINTS = (
    "en-gb",
    "en_gb",
    "english (united kingdom)",
    "english united kingdom",
    "british",
    "great britain",
    "uk ",
    " uk",
)
_MALE_NAME_HINTS = (
    "george",  # classic Windows UK male
    "ryan",
    "thomas",
    "david",  # often US male — weaker UK score but still male
    "mark",
    "ravi",
    "james",
    "oliver",
    "arthur",
)
_FEMALE_HINTS = (
    "female",
    "hazel",
    "susan",
    "zira",
    "sonia",
    "catherine",
    "aria",
    "jenny",
    "eva",
    "heera",
)


def is_female_voice_label(label: str) -> bool:
    s = (label or "").lower()
    return any(h in s for h in _FEMALE_HINTS)


def is_male_voice_label(label: str) -> bool:
    """True if label looks male and is not also tagged female."""
    s = (label or "").lower()
    if is_female_voice_label(s):
        return False
    if "male" in s:
        return True
    return any(h in s for h in _MALE_NAME_HINTS)


def score_windows_voice(label: str, *, prefer_hint: str = "") -> int:
    """Higher = better match for free Jarvis-style UK male."""
    s = (label or "").lower()
    score = 0
    if prefer_hint and prefer_hint.lower() in s:
        score += 100
    if any(h in s for h in _UK_HINTS):
        score += 50
    if "george" in s:
        score += 40  # classic Microsoft George (UK)
    if any(h in s for h in ("ryan", "thomas", "oliver", "arthur", "james")):
        score += 25
    if "david" in s or "mark" in s or "ravi" in s:
        score += 15  # male but often US
    if "male" in s:
        score += 20
    if is_female_voice_label(s):
        score -= 60
    if "en-us" in s or "english (united states)" in s:
        score -= 15
    return score


def _voice_parts(v) -> tuple[str | None, str]:
    if isinstance(v, tuple):
        return v[0], v[1] if len(v) > 1 else ""
    vid = getattr(v, "id", None)
    name = getattr(v, "name", "") or ""
    return vid, name


def pick_best_voice_id(voices: list, *, prefer_hint: str = "") -> str | None:
    """Pick best UK-male style voice.

    Never selects a female-labelled voice when any non-female candidate exists.
    Female-only inventories may still return the least-bad (highest score) voice.
    """
    scored: list[tuple[int, str, str]] = []
    for v in voices:
        vid, name = _voice_parts(v)
        if not vid:
            continue
        label = f"{name} {vid}"
        sc = score_windows_voice(label, prefer_hint=prefer_hint)
        scored.append((sc, str(vid), label))
    if not scored:
        return None

    non_female = [(sc, vid, lab) for sc, vid, lab in scored if not is_female_voice_label(lab)]
    # Prefer explicit male when present; else any non-female; else female-only least-bad
    males = [(sc, vid, lab) for sc, vid, lab in non_female if is_male_voice_label(lab)]
    if males:
        pool = males
    elif non_female:
        pool = non_female
    else:
        pool = scored  # female-only: document as least-bad fallback

    pool.sort(key=lambda x: x[0], reverse=True)
    return pool[0][1]


def pick_best_voice_name(voices: list, *, prefer_hint: str = "") -> str | None:
    """Same ranking as pick_best_voice_id but returns the display name when available."""
    best_id = pick_best_voice_id(voices, prefer_hint=prefer_hint)
    if not best_id:
        return None
    for v in voices:
        vid, name = _voice_parts(v)
        if str(vid) == str(best_id):
            return name or str(vid)
    return str(best_id)
