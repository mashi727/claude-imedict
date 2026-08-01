"""発話テキストから辞書登録候補語を抽出する。"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import kana, stoplist
from .tokenizer import KIND_ASCII, KIND_KANJI, KIND_KATAKANA, Token, tokenize

_CONTENT_JA = {KIND_KANJI, KIND_KATAKANA}
_RE_HIRA_TAIL = re.compile(f"[{kana.HIRAGANA}]$")
_RE_DIGITS = re.compile(r"^[0-9._-]+$")


@dataclass(slots=True)
class Candidate:
    word: str
    reading: str
    kind: str
    count: int = 0
    projects: set[str] = field(default_factory=set)
    standalone: int = 0  # 他の語の一部としてでなく単独で現れた回数
    parts: tuple[str, ...] = ()  # この語を構成した形態素
    confidence: str = "ok"  # low = 読みが文脈依存で揺れる形態素を含む

    @property
    def score(self) -> float:
        length_bonus = 1.0 + 0.25 * max(0, len(self.word) - 2)
        spread_bonus = 1.0 + 0.15 * (len(self.projects) - 1)
        return self.count * length_bonus * spread_bonus * math.log1p(self.count)


@dataclass(slots=True)
class ExtractConfig:
    min_count: int = 3
    min_projects: int = 1
    min_length: int = 3
    max_length: int = 24
    max_span_tokens: int = 3
    ascii_terms: bool = True
    japanese_terms: bool = True
    # 総出現のうち単独で現れた割合の下限。他語の内側にしか現れない
    # 切り出し過ぎの部分列 (「一次資料」由来の「次資料」等) を落とす。
    min_standalone_ratio: float = 0.2
    # 英字語の読みの作り方: lower=小文字綴り / letters=頭字語を一字ずつかな /
    # both=両方 (かな入力・英数入力のどちらからでも引ける)
    ascii_reading: str = "both"


def _chunks(tokens: list[Token]) -> list[list[Token]]:
    """連続する内容語トークンの塊に分ける。

    日本語 (漢字・カタカナ) と ASCII は読みの作り方が違うため混ぜない。
    トークン間に空白や記号があれば塊を切る。
    """
    chunks: list[list[Token]] = []
    cur: list[Token] = []
    cur_class = ""
    for tok in tokens:
        if tok.kind in _CONTENT_JA:
            cls = "ja"
        elif tok.kind == KIND_ASCII:
            cls = "ascii"
        else:
            cls = ""
        if not cls:
            if cur:
                chunks.append(cur)
            cur, cur_class = [], ""
            continue
        contiguous = bool(cur) and cur[-1].end == tok.start and cls == cur_class
        if contiguous:
            cur.append(tok)
        else:
            if cur:
                chunks.append(cur)
            cur, cur_class = [tok], cls
    if cur:
        chunks.append(cur)
    return chunks


def _spans(chunk: list[Token], max_span: int) -> list[list[Token]]:
    """塊から 1..max_span 語の連続部分列と、塊全体を取り出す。"""
    out: list[list[Token]] = []
    n = len(chunk)
    for size in range(1, min(max_span, n) + 1):
        for i in range(n - size + 1):
            out.append(chunk[i : i + size])
    if n > max_span:
        out.append(chunk)
    return out


def _ja_reading(span: list[Token]) -> str | None:
    parts = []
    for tok in span:
        r = tok.reading
        if not r:
            return None
        parts.append(r)
    reading = "".join(parts)
    return reading or None


def _accept_ja(word: str, reading: str, single_token: bool, cfg: ExtractConfig) -> bool:
    if not (cfg.min_length <= len(word) <= cfg.max_length):
        return False
    if stoplist.is_stopword(word):
        return False
    if len(reading) < 2:
        return False
    # 単独トークンで送り仮名終わりのものは活用形 (「行なっ」等) なので落とす
    if single_token and _RE_HIRA_TAIL.search(word):
        return False
    if kana.is_hiragana(word):
        return False
    return True


def _accept_ascii(word: str, cfg: ExtractConfig) -> bool:
    if not (cfg.min_length <= len(word) <= cfg.max_length):
        return False
    if _RE_DIGITS.match(word):
        return False
    if stoplist.is_stopword(word):
        return False
    # 全小文字なら読み (= 小文字化) と表記が一致し登録の意味がない
    return word != word.lower()


def extract(
    utterances,
    cfg: ExtractConfig | None = None,
    progress=None,
) -> list[Candidate]:
    cfg = cfg or ExtractConfig()
    table: dict[tuple[str, str], Candidate] = {}
    # 英字語は大文字小文字の揺れ (YouTube / Youtube) を束ねて多数派の綴りを採る
    ascii_forms: dict[str, Counter] = defaultdict(Counter)
    ascii_projects: dict[str, set[str]] = defaultdict(set)
    # 同じ漢字語でも文脈で読みが変わる (次 -> つぎ / じ)。揺れる形態素を
    # 含む語は読みの確度が低いので印を付ける。
    token_latin: dict[str, set[str]] = defaultdict(set)

    for idx, utt in enumerate(utterances):
        if progress and idx % 500 == 0:
            progress(idx)
        tokens = tokenize(utt.text)
        for tok in tokens:
            if tok.kind == KIND_KANJI and tok.latin:
                token_latin[tok.surface].add(tok.latin.lower())
        for chunk in _chunks(tokens):
            is_ascii = chunk[0].kind == KIND_ASCII
            if is_ascii and not cfg.ascii_terms:
                continue
            if not is_ascii and not cfg.japanese_terms:
                continue
            if is_ascii:
                # 連続 ASCII は結合して 1 語として扱う (PySide6 等)
                word = "".join(t.surface for t in chunk)
                if not _accept_ascii(word, cfg):
                    continue
                ascii_forms[word.lower()][word] += 1
                ascii_projects[word.lower()].add(utt.project)
                continue

            for span in _spans(chunk, cfg.max_span_tokens):
                word = "".join(t.surface for t in span)
                single = len(span) == 1
                reading = _ja_reading(span)
                if not reading:
                    continue
                if not _accept_ja(word, reading, single, cfg):
                    continue
                key = (word, reading)
                cand = table.get(key)
                if cand is None:
                    kind = KIND_KATAKANA if kana.is_katakana(word) else KIND_KANJI
                    cand = table[key] = Candidate(
                        word, reading, kind, parts=tuple(t.surface for t in span)
                    )
                cand.count += 1
                cand.projects.add(utt.project)
                if len(span) == len(chunk):
                    cand.standalone += 1

    # ほぼ常に他の語の内側にしか現れない部分列を落とす。
    # 例: 「一次資料」しか出現しないのに切り出される「次資料」。
    for key, cand in list(table.items()):
        if cand.standalone < max(1, cfg.min_standalone_ratio * cand.count):
            del table[key]
            continue
        if any(len(token_latin.get(p, ())) > 1 for p in cand.parts):
            cand.confidence = "low"

    for lower, forms in ascii_forms.items():
        total = sum(forms.values())
        surface = _canonical_ascii_form(forms)
        readings = []
        acro = kana.acronym_reading(surface)
        if cfg.ascii_reading in ("lower", "both"):
            readings.append(lower)
        if cfg.ascii_reading in ("letters", "both") and acro:
            readings.append(acro)
        if cfg.ascii_reading == "letters" and not acro:
            readings.append(lower)
        for reading in dict.fromkeys(readings):
            cand = Candidate(surface, reading, KIND_ASCII, total, set(ascii_projects[lower]))
            table[(surface, reading)] = cand

    cands = [
        c
        for c in table.values()
        if c.count >= cfg.min_count and len(c.projects) >= cfg.min_projects
    ]
    cands = _drop_subsumed(cands)
    cands.sort(key=lambda c: (-c.score, c.word))
    return cands


def _has_internal_upper(word: str) -> bool:
    """2 文字目以降に大文字を含むか (LuaTeX, azooKey, PySide のような綴り)。"""
    return any(c.isupper() for c in word[1:])


def _canonical_ascii_form(forms: Counter) -> str:
    """大文字小文字の揺れから正規の綴りを選ぶ。

    最頻形を基本としつつ、内部に大文字を持つ綴り (LuaTeX 等) は固有名詞の
    正式表記である可能性が高いので優遇する。ユーザー辞書の目的は
    「打鍵は小文字、確定は正式表記」なので、正式表記側に寄せるのが有益。
    """
    def weight(item: tuple[str, int]) -> tuple[float, int]:
        surface, count = item
        w = count * (1.5 if _has_internal_upper(surface) else 1.0)
        return (w, count)

    return max(forms.items(), key=weight)[0]


def _drop_subsumed(cands: list[Candidate]) -> list[Candidate]:
    """常に長い語の一部としてしか現れない短い語を落とす。

    例: 「協奏」が「協奏曲」の中にしか出現せず出現数も同じなら、
    「協奏」を単独で登録する必要はない。
    """
    by_len: dict[int, list[Candidate]] = defaultdict(list)
    for c in cands:
        by_len[len(c.word)].append(c)
    lengths = sorted(by_len)
    kept: list[Candidate] = []
    for c in cands:
        subsumed = False
        for ln in lengths:
            if ln <= len(c.word):
                continue
            for longer in by_len[ln]:
                if longer.count >= c.count and c.word in longer.word:
                    subsumed = True
                    break
            if subsumed:
                break
        if not subsumed:
            kept.append(c)
    return kept
