"""macOS の CFStringTokenizer を用いた日本語形態素分割と読み推定。

CFStringTokenizer は日本語ロケールで単語境界分割を行い、
kCFStringTokenizerAttributeLatinTranscription で各トークンのローマ字読みを
返す。漢字語の読み推定 (例: 協奏 -> kyousou) が得られるため、外部の
形態素解析器や辞書を追加インストールせずに読みを生成できる。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from . import kana

try:  # pragma: no cover - 実行環境依存
    # PyObjC はシンボルを実行時に生成するため静的解析が効かない。Any で受ける。
    CF: Any = importlib.import_module("CoreFoundation")
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pyobjc-core / pyobjc-framework-Cocoa が必要です。\n"
        "  pip install pyobjc-framework-Cocoa"
    ) from exc


KIND_KANJI = "kanji"
KIND_KATAKANA = "katakana"
KIND_HIRAGANA = "hiragana"
KIND_ASCII = "ascii"
KIND_OTHER = "other"


@dataclass(slots=True)
class Token:
    surface: str
    latin: str
    kind: str
    start: int = 0  # UTF-16 オフセット。隣接判定に使う
    end: int = 0

    @property
    def reading(self) -> str | None:
        """このトークンのひらがな読み。推定できなければ None。"""
        if self.kind == KIND_KATAKANA:
            return kana.katakana_to_hiragana(self.surface)
        if self.kind == KIND_HIRAGANA:
            return self.surface
        if self.kind == KIND_KANJI:
            return kana.romaji_to_hiragana(self.latin) if self.latin else None
        return None


def _classify(surface: str) -> str:
    if kana.is_katakana(surface):
        return KIND_KATAKANA
    if kana.is_hiragana(surface):
        return KIND_HIRAGANA
    if kana.has_kanji(surface):
        return KIND_KANJI
    if kana.is_ascii_word(surface):
        return KIND_ASCII
    return KIND_OTHER


_LOCALE = None


def _locale():
    global _LOCALE
    if _LOCALE is None:
        _LOCALE = CF.CFLocaleCreate(None, "ja_JP")
    return _LOCALE


def tokenize(text: str) -> list[Token]:
    """テキストを単語分割し、各トークンにローマ字読みを付与して返す。"""
    if not text:
        return []
    # CFRange は UTF-16 オフセットなので、サロゲートペアを含む文字列でも
    # 正しく切り出せるよう UTF-16LE のバイト列側でスライスする。
    u16 = text.encode("utf-16-le")
    length = len(u16) // 2
    tk = CF.CFStringTokenizerCreate(
        None, text, CF.CFRangeMake(0, length),
        CF.kCFStringTokenizerUnitWordBoundary, _locale(),
    )
    tokens: list[Token] = []
    while CF.CFStringTokenizerAdvanceToNextToken(tk):
        rng = CF.CFStringTokenizerGetCurrentTokenRange(tk)
        surface = u16[rng.location * 2 : (rng.location + rng.length) * 2].decode(
            "utf-16-le", "ignore"
        )
        if not surface:
            continue
        latin = CF.CFStringTokenizerCopyCurrentTokenAttribute(
            tk, CF.kCFStringTokenizerAttributeLatinTranscription
        )
        tokens.append(
            Token(
                surface,
                str(latin) if latin else "",
                _classify(surface),
                rng.location,
                rng.location + rng.length,
            )
        )
    return tokens
