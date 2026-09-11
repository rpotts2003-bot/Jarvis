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
    voice_hint: str = ""


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
_MALE_HINTS = (
    "male",
    "george",  # classic Windows UK male
    "ryan",
    "thomas",
    "sonia",  # skip — female; listed so we can downrank below
    "hazel",  # female UK
    "susan",
    "zira",
    "david",  # often US male — weaker UK score
    "mark",
    "ravi",
    "james",
    "oliver",
    "arthur",
)
_FEMALE_HINTS = ("female", "hazel", "susan", "zira", "sonia", "catherine", "aria", "jenny")


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
    if "male" in s:
        score += 20
    if any(h in s for h in _FEMALE_HINTS):
        score -= 60
    if "en-us" in s or "english (united states)" in s:
        score -= 15
    return score


def pick_best_voice_id(voices: list, *, prefer_hint: str = "") -> str | None:
    """voices: objects with .id and .name (pyttsx3) or (id, name) tuples."""
    best_id: str | None = None
    best = -10_000
    for v in voices:
        if isinstance(v, tuple):
            vid, name = v[0], v[1]
        else:
            vid = getattr(v, "id", None)
            name = getattr(v, "name", "") or ""
        if not vid:
            continue
        label = f"{name} {vid}"
        sc = score_windows_voice(label, prefer_hint=prefer_hint)
        if sc > best:
            best = sc
            best_id = vid
    return best_id if best > 0 else best_id  # still return best even if weak
