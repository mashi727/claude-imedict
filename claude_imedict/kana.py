"""ローマ字 <-> かな変換、および文字種判定。

CFStringTokenizer の Latin transcription はヘボン式に近い綴りを返す
(例: 協奏 -> "kyousou", 学習 -> "gakushuu", 圭太郎 -> "keitarou")。
長音が "ou" / "uu" と母音展開されるためワープロ式ローマ字としてそのまま
かなに戻せる。ここではその逆変換を最長一致で行う。
"""

from __future__ import annotations

import re
import unicodedata

# --- 文字種 ---------------------------------------------------------------

HIRAGANA = r"ぁ-ゟ"
KATAKANA = r"ァ-ヺーヽヾ"
KANJI = r"々一-鿿豈-﫿\U00020000-\U0002FFFF"

RE_HIRAGANA = re.compile(f"^[{HIRAGANA}ー]+$")
RE_KATAKANA = re.compile(f"^[{KATAKANA}]+$")
RE_KANJI = re.compile(f"^[{KANJI}]+$")
RE_HAS_KANJI = re.compile(f"[{KANJI}]")
RE_HAS_JA = re.compile(f"[{HIRAGANA}{KATAKANA}{KANJI}]")
RE_ASCII_WORD = re.compile(r"^[A-Za-z][A-Za-z0-9_+#.\-]*$")
RE_ALL_KANA = re.compile(f"^[{HIRAGANA}{KATAKANA}ー]+$")


def has_kanji(s: str) -> bool:
    return bool(RE_HAS_KANJI.search(s))


def has_japanese(s: str) -> bool:
    return bool(RE_HAS_JA.search(s))


def is_katakana(s: str) -> bool:
    return bool(RE_KATAKANA.match(s))


def is_hiragana(s: str) -> bool:
    return bool(RE_HIRAGANA.match(s))


def is_kana(s: str) -> bool:
    return bool(RE_ALL_KANA.match(s))


def is_ascii_word(s: str) -> bool:
    return bool(RE_ASCII_WORD.match(s))


def katakana_to_hiragana(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:
            out.append(chr(o - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def hiragana_to_katakana(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if 0x3041 <= o <= 0x3096:
            out.append(chr(o + 0x60))
        else:
            out.append(ch)
    return "".join(out)


# --- ローマ字 -> ひらがな --------------------------------------------------

_BASE = {
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "sa": "さ", "shi": "し", "si": "し", "su": "す", "se": "せ", "so": "そ",
    "za": "ざ", "ji": "じ", "zi": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "ta": "た", "chi": "ち", "ti": "ち", "tsu": "つ", "tu": "つ",
    "te": "て", "to": "と",
    "da": "だ", "di": "ぢ", "du": "づ", "de": "で", "do": "ど",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "fu": "ふ", "hu": "ふ", "he": "へ", "ho": "ほ",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "wa": "わ", "wi": "ゐ", "we": "ゑ", "wo": "を",
    "va": "ゔぁ", "vi": "ゔぃ", "vu": "ゔ", "ve": "ゔぇ", "vo": "ゔぉ",
    "n": "ん",
}

_YOON = {
    "ky": "き", "gy": "ぎ", "sh": "し", "sy": "し", "j": "じ", "zy": "じ",
    "ch": "ち", "ty": "ち", "cy": "ち", "dy": "ぢ", "ny": "に", "hy": "ひ",
    "by": "び", "py": "ぴ", "my": "み", "ry": "り", "fy": "ふ", "vy": "ゔ",
}
_SMALL = {"a": "ゃ", "u": "ゅ", "o": "ょ", "e": "ぇ", "i": "ぃ"}

# 拗音の展開 (kya -> きゃ 等)。sha/shu/sho, cha/chu/cho, ja/ju/jo も含む。
_TABLE: dict[str, str] = dict(_BASE)
for _cons, _lead in _YOON.items():
    for _v, _sm in _SMALL.items():
        if _cons in ("sh", "ch", "j") and _v == "i":
            continue  # shi/chi/ji は _BASE 側
        _TABLE.setdefault(_cons + _v, _lead + _sm)

# 外来語表記 (ICU が出しうるもの)
_TABLE.update({
    "fa": "ふぁ", "fi": "ふぃ", "fe": "ふぇ", "fo": "ふぉ",
    "ti": "てぃ", "di": "でぃ", "du": "どぅ", "tu": "つ",
    "che": "ちぇ", "she": "しぇ", "je": "じぇ",
    "wha": "うぁ", "whi": "うぃ", "whe": "うぇ", "who": "うぉ",
    "kwa": "くぁ", "gwa": "ぐぁ",
    # ICU は四つ仮名を dz/dj で綴る (日付 -> hidzuke)
    "dzu": "づ", "dzi": "ぢ", "dji": "ぢ", "dja": "ぢゃ",
    "dju": "ぢゅ", "djo": "ぢょ",
    # ICU は小書き仮名を "~" 前置で表す (行なっ -> okona~tsu)
    "~tsu": "っ", "~tu": "っ", "~ya": "ゃ", "~yu": "ゅ", "~yo": "ょ",
    "~a": "ぁ", "~i": "ぃ", "~u": "ぅ", "~e": "ぇ", "~o": "ぉ",
    "~wa": "ゎ", "~ka": "ゕ", "~ke": "ゖ",
})

_MAX_LEN = max(len(k) for k in _TABLE)
_VOWELS = set("aiueo")


def romaji_to_hiragana(romaji: str) -> str | None:
    """ワープロ式ローマ字をひらがなへ。変換不能な文字が残る場合は None。"""
    if not romaji:
        return None
    s = unicodedata.normalize("NFKC", romaji).lower()
    s = s.replace("’", "'").replace("-", "")
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "'":
            i += 1
            continue
        # 撥音: n の直後が母音・y・' 以外なら「ん」
        if ch == "n" and (i + 1 >= n or (s[i + 1] not in _VOWELS and s[i + 1] != "y")):
            out.append("ん")
            i += 1
            continue
        # 促音: 同一子音の連続 (tch は「っ」+「ち」)
        if ch not in _VOWELS and i + 1 < n:
            if s[i + 1] == ch and ch != "n":
                out.append("っ")
                i += 1
                continue
            if ch == "t" and s[i + 1 : i + 3] == "ch":
                out.append("っ")
                i += 1
                continue
        matched = False
        for ln in range(min(_MAX_LEN, n - i), 0, -1):
            kana = _TABLE.get(s[i : i + ln])
            if kana:
                out.append(kana)
                i += ln
                matched = True
                break
        if not matched:
            return None
    return "".join(out)


def normalize_reading(reading: str) -> str:
    """読みをひらがなへ正規化する。"""
    r = unicodedata.normalize("NFKC", reading).strip()
    r = katakana_to_hiragana(r)
    return r


# --- 頭字語の読み上げ ------------------------------------------------------

# 日本語話者が英字の頭字語を打つときのかな (URL -> ゆーあーるえる)
_LETTER_KANA = {
    "a": "えー", "b": "びー", "c": "しー", "d": "でぃー", "e": "いー",
    "f": "えふ", "g": "じー", "h": "えいち", "i": "あい", "j": "じぇー",
    "k": "けー", "l": "える", "m": "えむ", "n": "えぬ", "o": "おー",
    "p": "ぴー", "q": "きゅー", "r": "あーる", "s": "えす", "t": "てぃー",
    "u": "ゆー", "v": "ぶい", "w": "だぶりゅー", "x": "えっくす",
    "y": "わい", "z": "ぜっと",
    "0": "ぜろ", "1": "いち", "2": "に", "3": "さん", "4": "よん",
    "5": "ご", "6": "ろく", "7": "なな", "8": "はち", "9": "きゅう",
}


def acronym_reading(word: str) -> str | None:
    """全大文字の頭字語を一字ずつ読み上げたかなにする。該当しなければ None。"""
    if not (2 <= len(word) <= 6):
        return None
    if not word.isupper() and not all(c.isupper() or c.isdigit() for c in word):
        return None
    if not any(c.isalpha() for c in word):
        return None
    out = []
    for ch in word.lower():
        k = _LETTER_KANA.get(ch)
        if not k:
            return None
        out.append(k)
    return "".join(out)
