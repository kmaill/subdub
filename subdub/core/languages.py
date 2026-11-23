from dataclasses import dataclass

@dataclass(frozen=True)
class LanguageSpec:
    code_3: str         # ISO 639-2 for mp4
    code_2: str         # ISO 639-1 for subtitles
    name: str           # metadata names
    voice_label: str    # voiceover label
    keywords: tuple[str, ...]       # keywords in audio and subtitles

KNOWN_LANGUAGES: dict[str, LanguageSpec] = {                                                                                                                                      
    "pol": LanguageSpec("pol", "pl", "Polski", "Lektor AI", ("polski", "polish", "lektor", "dubbing", "pl", "pol")),
    "eng": LanguageSpec("eng", "en", "English", "AI Voiceover", ("english", "eng", "en")),
    "spa": LanguageSpec("spa", "es", "Español", "Voz AI", ("spanish", "español", "espanol", "castellano", "spa", "es")),
    "deu": LanguageSpec("deu", "de", "Deutsch", "KI-Stimme", ("german", "deutsch", "deu", "ger", "de")),
    "fra": LanguageSpec("fra", "fr", "Français", "Voix IA", ("french", "français", "francais", "fra", "fre", "fr")),
    "ukr": LanguageSpec("ukr", "uk", "Українська", "АІ Голос", ("ukrainian", "українська", "ukr", "uk")),
    "ita": LanguageSpec("ita", "it", "Italiano", "Voce AI", ("italian", "italiano", "ita", "it")),
}

ALIASES: dict[str, str] = {
    "pl": "pol", "en": "eng", "es": "spa", "de": "deu", "ger": "deu",
    "fr": "fra", "fre": "fra", "uk": "ukr", "ua": "ukr", "it": "ita",
}

def resolve_language(lang_input: str) -> LanguageSpec:
    raw = lang_input.strip().lower()
    if "-" in raw:
        raw = raw.split("-")[0]
    
    canonical = ALIASES.get(raw, raw)
    if canonical in KNOWN_LANGUAGES:
        return KNOWN_LANGUAGES[canonical]
    
    # Fallback for any language
    code_3 = canonical if len(canonical) == 3 else canonical[:3]
    code_2 = canonical[:2]
    return LanguageSpec(
        code_3=code_3,
        code_2=code_2,
        name=canonical.upper(),
        voice_label="AI Voiceover",
        keywords=(canonical, code_2, code_3),
    )