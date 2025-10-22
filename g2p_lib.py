# Neutral Spanish grapheme→phoneme (IPA-ish) with stress marker ˈ.
# Design goals:
#  - NEVER emit accented characters (áéíóú) in the final output
#  - "Plan B": insert spaces around punctuation so it never attaches to words
#  - Use ASCII 'x' for the velar fricative (j / g + e,i)
#  - By default: NO nasal assimilation (n stays 'n'), SAFE glide mode

import re
import unicodedata
from typing import List

# ---------------- Configuration knobs ----------------
NASAL_ASSIMILATION = False   # True -> n→ŋ before g/k/qu/c(+a/o/u)
GLIDE_MODE = "safe"          # "safe": only hi/hu→j/w; "full": also diphthong i/u rules

# ---------------- Char classes ----------------
VOWELS = "aeiou"
VOWELS_ACCENTED = "áéíóú"
ALL_VOWELS = VOWELS + VOWELS_ACCENTED
ACUTE_MAP = str.maketrans(VOWELS_ACCENTED, VOWELS)
ACCENT_VOWEL_MAP = {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú'}

# Punctuation to split (Plan B). Add '-' if you also want to hard-split hyphens.
_PUNCT_CHARS = ',.;:¡!¿?()[]{}"«»“”—–…'
_PUNCT_RE = re.compile(rf'([{re.escape(_PUNCT_CHARS)}])')
_PUNCT_SET = set(_PUNCT_CHARS)

# ---------------- Utilities ----------------
def _normalize_nfc(text: str) -> str:
    return unicodedata.normalize('NFC', text)

def _space_punct(text: str) -> str:
    # Insert spaces around punctuation so it never touches words
    text = _PUNCT_RE.sub(r' \1 ', text)
    # Split ellipsis if present
    text = re.sub(r'\.\.\.', ' . . . ', text)
    # Collapse whitespace
    return re.sub(r'\s+', ' ', text).strip()

def normalize_word(word: str) -> str:
    return word.lower()

def strip_accents(s: str) -> str:
    return s.translate(ACUTE_MAP)

# ---------------- Core mapping ----------------
def map_graphemes(word: str) -> str:
    """
    Orthography → phone-like symbols (subset compatible with your token map).
    Rules: ch→ʧ; initial x→s else x→ks; j/g(+e,i)→x; gu+e/i→g; z/ce/ci→s; c→k;
           qu+e/i→k; v→b; h silent; hi/hu+V→j/w; ñ→ɲ; ll/y→ʝ or j (final glide);
           word-initial r or rr or lr/nr/sr → r; other r→ɾ; final n stays 'n'
           (unless NASAL_ASSIMILATION=True).
    """
    w = normalize_word(word)

    # Optional nasal assimilation BEFORE other mappings
    if NASAL_ASSIMILATION:
        w = re.sub(r'n(?=g)', 'ŋ', w)
        w = re.sub(r'n(?=k)', 'ŋ', w)
        w = re.sub(r'n(?=qu)', 'ŋ', w)
        w = re.sub(r'n(?=c(?=[aouáóú]))', 'ŋ', w)

    # standalone conjunction "y" => /i/
    if w == 'y':
        return 'i'

    # ch → ʧ
    w = w.replace("ch", "ʧ")

    # x rules
    if w.startswith("x"):
        w = "s" + w[1:]          # initial x ≈ /s/
    w = w.replace("x", "ks")     # elsewhere /ks/

    # j / g before e,i → x  (ASCII 'x' for velar fricative)
    w = re.sub(r"g(?=[eéií])", "x", w)
    w = w.replace("j", "x")

    # gu + e/i (no diaeresis) → g
    w = re.sub(r"gu(?=[eéií])", "g", w)
    w = w.replace("gü", "gw")

    # c / z / qu rules
    w = re.sub(r"c(?=[eéií])", "s", w)   # ce/ci => s
    w = w.replace("z", "s")
    w = w.replace("c", "k")              # elsewhere => k
    w = re.sub(r"qu(?=[eéií])", "k", w)

    # v → b
    w = w.replace("v", "b")

    # hi/hu before vowel → j/w ; plain h silent
    w = re.sub(r"hi(?=[" + ALL_VOWELS + "])", "j", w)
    w = re.sub(r"hu(?=[" + ALL_VOWELS + "])", "w", w)
    w = w.replace("h", "")

    # ñ → ɲ
    w = w.replace("ñ", "ɲ")

    # ll / y → ʝ (yeísmo); vowel+y (final) → glide j
    w = w.replace("ll", "ʝ")
    w = re.sub(r"^y(?=[" + ALL_VOWELS + "])", "ʝ", w)
    w = re.sub(r"(?<=[^" + ALL_VOWELS + "])y(?=[" + ALL_VOWELS + "])", "ʝ", w)
    w = re.sub(r"(?<=[" + ALL_VOWELS + "])y$", "j", w)

    # word-final n: keep as 'n' by default (assimilation off)
    if NASAL_ASSIMILATION and w.endswith('n'):
        # if you prefer final 'ŋ' when assimilation is enabled:
        w = w[:-1] + 'ŋ'

    # r/rr and onset-r strengthening
    placeholder = "RRR"
    w = w.replace("rr", placeholder)
    if w.startswith("r"):
        w = placeholder + w[1:]
    w = re.sub(r"([lns])r", r"\1" + placeholder, w)  # lr/nr/sr clusters
    w = w.replace("r", "ɾ")
    w = w.replace(placeholder, "r")

    return w

def add_stress_if_needed(phonemes: str) -> str:
    """
    If there is an accented vowel (áéíóú), keep it (orthographic stress).
    Otherwise apply default: penult if ends in vowel/N/S, else final.
    We mark stress by temporarily accenting a vowel; we'll convert to ˈ later.
    """
    if any(v in phonemes for v in VOWELS_ACCENTED):
        return phonemes

    # rough syllable proxy: count vowel groups
    groups = list(re.finditer(f"[{ALL_VOWELS}]+", phonemes))
    if len(groups) <= 1:
        return phonemes

    ends_like_penult = phonemes.endswith(tuple(VOWELS)) or phonemes.endswith(('n', 's'))
    target_idx = len(groups) - (2 if ends_like_penult else 1)
    if target_idx < 0:
        target_idx = 0

    g = groups[target_idx]
    # accent the first plain vowel in that group
    for j in range(g.start(), g.end()):
        ch = phonemes[j]
        if ch in VOWELS:
            return phonemes[:j] + ACCENT_VOWEL_MAP[ch] + phonemes[j+1:]
    return phonemes

def apply_glides(phonemes: str) -> str:
    """
    GLIDE_MODE:
      - "safe": only keep hi/hu→j/w done earlier; do not force generic i/u glides
      - "full": also convert i/u to glides in diphthong contexts (unaccented only)
    """
    if GLIDE_MODE != "full":
        return phonemes

    # Only touch unaccented i/u
    # i before AEO (with/without accents) → j
    phonemes = re.sub(r"i(?=[aeoáéó])", "j", phonemes)
    # u before any vowel (accented or not) → w
    phonemes = re.sub(r"u(?=[aeioáéíó])", "w", phonemes)
    # after vowels
    phonemes = re.sub(r"(?<=[aeoáéó])i", "j", phonemes)
    phonemes = re.sub(r"(?<=[aeioáéíó])u", "w", phonemes)
    return phonemes

def insert_stress_marker_and_clean(phonemes: str) -> str:
    """
    Find any accented vowel, insert ˈ just before the nucleus (and before a
    preceding j/w glide if present), then strip accent diacritics globally.
    Output contains NO áéíóú — only base vowels plus ˈ.
    """
    m = re.search(r"[áéíóú]", phonemes)
    if not m:
        return strip_accents(phonemes)

    pos = m.start()
    start_pos = pos
    if pos > 0 and phonemes[pos - 1] in "jw":
        start_pos = pos - 1

    base = strip_accents(phonemes[pos])
    out = phonemes[:start_pos] + "ˈ" + phonemes[start_pos:pos] + base + phonemes[pos+1:]
    return strip_accents(out)

# ---------------- Public API ----------------
def g2p(text: str) -> str:
    """
    Convert Spanish text to phones with a leading ˈ on the stressed syllable.
    Punctuation is spaced out (Plan B). Final string never has áéíóú.
    """
    if not text:
        return "//"

    text = _normalize_nfc(text)
    text = _space_punct(text)

    out: List[str] = []
    for tok in text.split(" "):
        if not tok:
            continue
        if set(tok) <= _PUNCT_SET:
            out.append(tok)
            continue

        p1 = map_graphemes(tok)
        p2 = add_stress_if_needed(p1)
        p3 = apply_glides(p2)
        p4 = insert_stress_marker_and_clean(p3)
        out.append(p4)

    result = " ".join(out).strip()
    return f"/ {result} /" if result else "//"
