"""xAI Voice constants (TTS / STT)."""

from __future__ import annotations

import re

from homeassistant.components.tts import ATTR_VOICE

# Config option keys
CONF_TTS_VOICE = "tts_voice"
CONF_TTS_LANGUAGE = "tts_language"
CONF_TTS_SPEED = "tts_speed"
CONF_STT_LANGUAGE = "stt_language"
CONF_STT_FORMAT = "stt_format"
CONF_STT_KEYTERMS = "stt_keyterms"
CONF_ENABLE_TTS = "enable_tts"
CONF_ENABLE_STT = "enable_stt"
CONF_VOICE_API_OK = "voice_api_ok"

RECOMMENDED_TTS_VOICE = "eve"
RECOMMENDED_TTS_LANGUAGE = "en"
RECOMMENDED_TTS_SPEED = 1.0
RECOMMENDED_STT_LANGUAGE = "en"
RECOMMENDED_STT_KEYTERMS = ""
RECOMMENDED_ENABLE_TTS = True
RECOMMENDED_ENABLE_STT = True

XAI_API_BASE = "https://api.x.ai/v1"
XAI_TTS_URL = f"{XAI_API_BASE}/tts"
XAI_STT_URL = f"{XAI_API_BASE}/stt"
XAI_VOICES_URL = f"{XAI_API_BASE}/tts/voices"

# STT keyterm limits from https://docs.x.ai/developers/rest-api-reference/inference/speech-to-text
# (``keyterm`` form field, repeatable: max 100 terms, each up to 50 characters).
STT_KEYTERM_MAX_COUNT = 100
STT_KEYTERM_MAX_LENGTH = 50

# Built-in voices from xAI docs (voice_id → display label)
XAI_VOICES: dict[str, str] = {
    "eve": "Eve — energetic and upbeat",
    "ara": "Ara — warm and friendly",
    "rex": "Rex — confident and clear",
    "sal": "Sal — smooth and balanced",
    "leo": "Leo — authoritative and strong",
    "carina": "Carina — soft, empathetic",
    "luna": "Luna — gentle, patient",
    "iris": "Iris — friendly, upbeat",
    "helios": "Helios — upbeat, versatile assistant",
    "celeste": "Celeste — compassionate, reassuring",
    "ursa": "Ursa — friendly, warm",
    "rigel": "Rigel — precise, professional",
    "cosmo": "Cosmo — bright, curious",
    "lux": "Lux — grounded, calm",
    "atlas": "Atlas — confident, commanding",
    "castor": "Castor — charismatic, easygoing",
    "naksh": "Naksh — warm, thoughtful",
    "lumen": "Lumen — warm, articulate",
    "sirius": "Sirius — quick-witted, playful",
    "orion": "Orion — rich, cinematic",
    "altair": "Altair — elegant, premium",
    "perseus": "Perseus — strong, trustworthy",
    "zenith": "Zenith — sharp, focused",
    "helix": "Helix — bold, dynamic",
    "kepler": "Kepler — inventive, charismatic",
    "zagan": "Zagan — powerful, dramatic",
}

# TTS languages (BCP-47). HA Assist language dropdown uses these codes.
# Include both short and locale forms commonly used by Assist.
TTS_LANGUAGES: list[str] = [
    "en",
    "en-US",
    "en-GB",
    "ar-EG",
    "ar-SA",
    "ar-AE",
    "bn",
    "zh",
    "zh-CN",
    "fr",
    "fr-FR",
    "de",
    "de-DE",
    "hi",
    "id",
    "it",
    "it-IT",
    "ja",
    "ja-JP",
    "ko",
    "ko-KR",
    "pt-BR",
    "pt-PT",
    "ru",
    "ru-RU",
    "es",
    "es-ES",
    "es-MX",
    "tr",
    "vi",
    "auto",
]

# STT languages from xAI docs (25+)
STT_LANGUAGES: list[str] = [
    "en",
    "en-US",
    "en-GB",
    "ar",
    "cs",
    "da",
    "nl",
    "fil",
    "fr",
    "fr-FR",
    "de",
    "de-DE",
    "hi",
    "id",
    "it",
    "it-IT",
    "ja",
    "ja-JP",
    "ko",
    "ko-KR",
    "mk",
    "ms",
    "fa",
    "pl",
    "pt",
    "pt-BR",
    "ro",
    "ru",
    "ru-RU",
    "es",
    "es-ES",
    "es-MX",
    "sv",
    "th",
    "tr",
    "vi",
]

# Map HA Assist locale → xAI language param
def normalize_tts_language(language: str | None) -> str:
    """Normalize HA language code to xAI TTS language."""
    if not language:
        return RECOMMENDED_TTS_LANGUAGE
    lang = language.replace("_", "-").strip()
    if lang.lower() == "auto":
        return "auto"
    # Exact match
    for supported in TTS_LANGUAGES:
        if supported.lower() == lang.lower():
            return supported if supported != "auto" else "auto"
    # Primary subtag
    primary = lang.split("-")[0].lower()
    for supported in TTS_LANGUAGES:
        if supported.lower() == primary:
            return supported
    # English display name from some STT UIs
    if lang.lower() in ("english", "en_us", "en_gb"):
        return "en"
    return primary or RECOMMENDED_TTS_LANGUAGE


def normalize_stt_language(language: str | None) -> str | None:
    """Normalize HA language for STT formatting (primary subtag)."""
    if not language:
        return RECOMMENDED_STT_LANGUAGE
    lang = language.replace("_", "-").strip()
    lower = lang.lower()
    if lower in ("auto",):
        return None
    if lower in ("english",):
        return "en"
    primary = lang.split("-")[0].lower()
    # Valid STT primary codes from docs
    known = {
        "ar", "cs", "da", "nl", "en", "fil", "fr", "de", "hi", "id", "it",
        "ja", "ko", "mk", "ms", "fa", "pl", "pt", "ro", "ru", "es", "sv",
        "th", "tr", "vi",
    }
    if primary in known:
        return primary
    return primary or RECOMMENDED_STT_LANGUAGE


def split_stt_keyterms(raw: str | list[str] | None) -> list[str]:
    """Split a keyterm option (newline/comma separated text or list) into terms.

    Whitespace is collapsed, blanks are dropped and duplicates are removed
    case-insensitively (first spelling wins). Limits are not applied here.
    """
    if not raw:
        return []
    items = raw if isinstance(raw, list) else re.split(r"[\n,;]+", str(raw))
    terms: list[str] = []
    seen: set[str] = set()
    for item in items:
        term = " ".join(str(item).split())
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def parse_stt_keyterms(raw: str | list[str] | None) -> list[str]:
    """Return keyterms ready to send to xAI STT, enforcing documented limits.

    Terms longer than ``STT_KEYTERM_MAX_LENGTH`` are skipped (a truncated
    term would bias toward the wrong word) and at most
    ``STT_KEYTERM_MAX_COUNT`` terms are returned.
    """
    terms = [
        t for t in split_stt_keyterms(raw) if len(t) <= STT_KEYTERM_MAX_LENGTH
    ]
    return terms[:STT_KEYTERM_MAX_COUNT]


# Re-export for options
TTS_VOICE_OPTION = ATTR_VOICE  # "voice" — required by Assist UI
