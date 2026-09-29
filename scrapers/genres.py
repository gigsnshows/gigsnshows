"""
Genres within each category, for the dashboard's filter chips and "For you", and the
language a show is performed in.

None of the sources label genres consistently, so a show is tagged from the words in its
title, description and venue. A show can have several genres, or none (it then only
appears under "All"). Order here is the order chips appear in onboarding.

To add a genre: add a line (slug, label, [keywords]) under its category. Slugs must be
unique across categories; keywords match whole words, case-insensitively. Language
genres (Hindi, Marathi…) have no keywords of their own: they come from `language()`.
"""

import re

GENRES = {
    "music": [
        ("bollywood", "Bollywood", ["bollywood", "filmy", "hindi retro", "retro night", "90s night", "arijit", "kishore kumar"]),
        ("rock", "Rock", ["rock", "grunge", "punk", "rock n roll"]),
        ("metal", "Metal", ["metal", "metalcore", "thrash", "death metal", "doom"]),
        ("pop", "Pop", ["pop", "k-pop", "kpop", "pop star"]),
        ("hiphop", "Hip-hop & R&B", ["hip hop", "hip-hop", "hiphop", "rap", "rapper", "trap", "r&b", "rnb", "desi hip hop"]),
        ("electronic", "Electronic", ["edm", "techno", "house", "trance", "psytrance", "dj", "electronic", "electronica",
                                      "drum and bass", "dnb", "dubstep", "afro house", "rave", "club night", "bass music"]),
        ("jazz", "Jazz & blues", ["jazz", "blues", "swing", "soul", "funk", "bebop"]),
        ("indie", "Indie & acoustic", ["indie", "alternative", "singer-songwriter", "acoustic", "unplugged", "lo-fi"]),
        ("western-classical", "Western classical", ["orchestra", "symphony", "philharmonic", "piano recital", "chamber",
                                                     "opera", "string quartet", "western classical", "concerto", "choir"]),
        ("indian-classical", "Indian classical", ["hindustani", "carnatic", "raag", "raga", "sitar", "tabla", "sarod",
                                                  "santoor", "veena", "dhrupad", "khayal", "thumri", "indian classical", "jugalbandi"]),
        ("sufi", "Sufi & ghazal", ["sufi", "qawwali", "ghazal", "ghazals", "sufiana"]),
        ("folk", "Folk & world", ["folk", "baul", "rajasthani", "bhangra", "world music", "flamenco", "reggae", "latin"]),
        ("devotional", "Devotional", ["bhajan", "bhajans", "kirtan", "devotional", "satsang", "aarti", "bhakti"]),
        ("tribute", "Tributes & covers", ["tribute", "tributes", "cover band", "covers", "the music of"]),
        ("open-jam", "Karaoke, jams & open mics", ["karaoke", "jam", "jamming", "jam session", "open mic", "open-mic"]),
    ],
    "theatre": [
        ("drama", "Drama", ["drama", "tragedy", "thriller", "mystery"]),
        ("comedy-play", "Comedy plays", ["comedy", "comic", "farce", "hilarious", "laugh"]),
        ("musical", "Musicals", ["musical", "musicals", "opera"]),
        # Not plain "family": "a family drama" is a play about a family, not one for kids.
        ("kids", "Kids & family", ["kids", "for children", "children's", "children’s", "family show", "family-friendly",
                                   "family friendly", "all ages", "puppet", "puppetry", "fairy tale"]),
        ("storytelling", "Storytelling & poetry", ["storytelling", "story telling", "dastangoi", "poetry", "poem",
                                                   "spoken word", "mushaira", "kavi sammelan", "open mic"]),
        ("dance", "Dance", ["dance", "ballet", "kathak", "bharatanatyam", "odissi", "kuchipudi", "contemporary dance"]),
        ("theatre-hindi", "Hindi", []),
        ("theatre-english", "English", []),
        ("theatre-marathi", "Marathi", []),
        ("theatre-gujarati", "Gujarati", []),
        ("theatre-regional", "Other Indian languages", []),
    ],
    "sports": [
        ("running", "Running", ["marathon", "half marathon", "10k", "5k", "21k", "run", "runs", "running", "ultra", "trail run"]),
        ("cycling", "Cycling", ["cycling", "cyclothon", "cycle", "pedal"]),
        ("cricket", "Cricket", ["cricket", "t20", "t20i", "odi", "ipl", "test match"]),
        ("football", "Football", ["football", "fifa", "isl", "futsal", "soccer"]),
        ("racquet", "Tennis, padel & badminton", ["tennis", "padel", "badminton", "pickleball", "squash", "table tennis"]),
        ("combat", "Combat sports", ["mma", "boxing", "wrestling", "ufc", "kickboxing", "fight night", "fight"]),
        ("games", "Chess & board games", ["chess", "board game", "board games", "boardgame", "boardgames", "quiz", "poker"]),
        ("motorsport", "Motorsport & karting", ["karting", "go-kart", "go kart", "motorsport", "racing", "f1", "motocross",
                                                "dirt track", "motoverse", "superbike"]),
        ("fitness", "Fitness", ["hyrox", "zumba", "yoga", "crossfit", "bootcamp", "workout", "fitness", "zumbathon"]),
        ("outdoors", "Outdoors & adventure", ["trek", "trekking", "hike", "hiking", "kayaking", "rafting", "climbing", "camping"]),
        ("esports", "Esports & gaming", ["esports", "e-sports", "gaming", "bgmi", "valorant", "fifa tournament"]),
    ],
    "comedy": [
        ("standup", "Stand-up", ["stand-up", "standup", "stand up", "comedy show", "comedy special", "live comedy"]),
        ("improv", "Improv", ["improv", "improvisation", "improvised"]),
        ("comedy-open-mic", "Open mics & new material", ["open mic", "open-mic", "new material", "trial show",
                                                         "work in progress", "wip", "trial"]),
        ("crowdwork", "Crowd work & roasts", ["crowd work", "crowdwork", "roast", "roasts"]),
        ("comedy-hindi", "Hindi", []),
        ("comedy-english", "English", []),
        ("comedy-regional", "Other Indian languages", []),
    ],
}

# The genre each language files under, per category (comedy lumps the regional ones together).
LANGUAGE_GENRES = {
    "theatre": {"english": "theatre-english", "hindi": "theatre-hindi", "marathi": "theatre-marathi",
                "gujarati": "theatre-gujarati", "other": "theatre-regional"},
    "comedy": {"english": "comedy-english", "hindi": "comedy-hindi", "marathi": "comedy-regional",
               "gujarati": "comedy-regional", "other": "comedy-regional"},
}

LANGUAGES = [
    ("english", "English", ["english"]),
    ("hindi", "Hindi", ["hindi", "hinglish"]),
    ("marathi", "Marathi", ["marathi"]),
    ("gujarati", "Gujarati", ["gujarati", "gujju", "gujjubhai"]),
    ("other", "Other Indian languages", ["kannada", "tamil", "telugu", "bengali", "bangla", "malayalam", "punjabi",
                                         "urdu", "konkani", "sindhi", "odia", "assamese"]),
]
# Mumbai and Pune's natyagruhas stage Marathi plays almost every night; used only when a
# play's own title and description don't name a language.
MARATHI_STAGES = re.compile(r"\b(natya ?gru?ha|natya ?grih|natya ?mandir|rangayatan|shivaji mandir|bal ?gandharva|prabodhankar|"
                            r"ghanekar|tilak smarak)", re.I)
GUJARATI_SCRIPT = re.compile(r"[\u0A80-\u0AFF]")
# "With English subtitles" says nothing about the language on stage.
SUBTITLES = re.compile(r"\b\w+\s+(?:sub|sur)-?titles?\b", re.I)


def _pattern(words):
    return re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(words, key=len, reverse=True)) + r")\b", re.I)


_PATTERNS = {cat: [(slug, _pattern(words)) for slug, _, words in entries if words] for cat, entries in GENRES.items()}
_LANG_PATTERNS = [(slug, _pattern(words)) for slug, _, words in LANGUAGES]


def language(category, title, about="", venue=""):
    """
    Languages a show is performed in, e.g. ["marathi"]; empty when nothing says. The title
    decides if it names one; otherwise, for plays and stand-up, the language(s) the
    description mentions most; then, for plays, the stage it's on.
    """
    in_title = [slug for slug, rx in _LANG_PATTERNS if rx.search(title or "")]
    if in_title:
        return in_title
    if GUJARATI_SCRIPT.search(title or ""):
        return ["gujarati"]
    if category not in ("theatre", "comedy"):
        return []  # a gig's blurb mentioning "English" or "Punjabi" rarely means the language it's sung in
    text = SUBTITLES.sub(" ", about or "")
    counts = {slug: len(rx.findall(text)) for slug, rx in _LANG_PATTERNS}
    top = max(counts.values())
    if top:
        return [slug for slug, n in counts.items() if n == top]
    if category == "theatre" and MARATHI_STAGES.search(venue or ""):
        return ["marathi"]
    return []


def tag(category, title, about="", langs=()):
    """
    Genre slugs for a show. A title that names genres wins outright. Otherwise the
    description decides, keeping only the one or two genres it mentions most — long
    descriptions name-drop plenty ("soulful", "orchestra", "DJ") that isn't the show.
    The show's language (`langs`, from language()) is added on top, never crowded out.
    """
    pats = _PATTERNS.get(category, [])
    in_title = [slug for slug, rx in pats if rx.search(title or "")]
    if in_title:
        found = in_title
    else:
        counts = [(len(rx.findall(about or "")), i, slug) for i, (slug, rx) in enumerate(pats)]
        ranked = sorted((c for c in counts if c[0]), key=lambda c: (-c[0], c[1]))
        found = [slug for _, _, slug in ranked[:2]]
    by_lang = LANGUAGE_GENRES.get(category, {})
    for lang in langs:
        if lang in by_lang and by_lang[lang] not in found:
            found.append(by_lang[lang])
    return found


def catalog():
    """{category: [[slug, label], ...]} for the dashboard."""
    return {cat: [[slug, label] for slug, label, _ in entries] for cat, entries in GENRES.items()}


def languages():
    """[[slug, label], ...] for the dashboard's language choice."""
    return [[slug, label] for slug, label, _ in LANGUAGES]
