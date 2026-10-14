"""The reply language setting and the metadata locale it implies."""

from __future__ import annotations

from typing import Optional

# Language name → ISO 639-1, for TMDB/Seerr metadata (titles and overviews).
CODES = {
    "Arabic": "ar", "Bulgarian": "bg", "Chinese": "zh", "Croatian": "hr", "Czech": "cs", "Danish": "da",
    "Dutch": "nl", "English": "en", "Finnish": "fi", "French": "fr", "German": "de", "Greek": "el",
    "Hebrew": "he", "Hindi": "hi", "Hungarian": "hu", "Indonesian": "id", "Italian": "it", "Japanese": "ja",
    "Korean": "ko", "Norwegian": "no", "Persian": "fa", "Polish": "pl", "Portuguese": "pt", "Romanian": "ro",
    "Russian": "ru", "Serbian": "sr", "Slovak": "sk", "Spanish": "es", "Swedish": "sv", "Thai": "th",
    "Turkish": "tr", "Ukrainian": "uk", "Vietnamese": "vi",
}


def reply_language(setting: Optional[str]) -> Optional[str]:
    """The language to answer in, or None to follow the user.

    >>> reply_language("auto"), reply_language(" Turkish "), reply_language("")
    (None, 'Turkish', None)
    """
    value = (setting or "").strip()
    return None if not value or value.lower() == "auto" else value


def metadata_code(setting: Optional[str]) -> str:
    """ISO 639-1 for metadata; English when unknown or automatic.

    >>> metadata_code("Turkish"), metadata_code("auto"), metadata_code("Klingon"), metadata_code("pt")
    ('tr', 'en', 'en', 'pt')
    """
    lang = reply_language(setting)
    if not lang:
        return "en"
    if lang.lower() in CODES.values():
        return lang.lower()
    return CODES.get(lang.title(), "en")
