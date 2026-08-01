"""抽出した候補語を各 IME のユーザー辞書形式へ書き出す。

macOS 標準 (テキスト置換 / 日本語入力のユーザ辞書):
    <array> に {shortcut: 読み, phrase: 表記} の <dict> を並べた plist。
    システム設定 > キーボード > テキスト入力 > テキスト置換 に
    ドラッグ&ドロップして取り込む。

azooKey (macOS 版):
    UserDefaults キー
    dev.ensan.inputmethod.azooKeyMac.preference.user_dictionary_temporal2
    に格納される JSON 文字列。{"items": [{word, reading, hint, id}]} 形式。
"""

from __future__ import annotations

import csv
import hashlib
import json
import plistlib
import uuid
from pathlib import Path
from typing import Iterable, Sequence

from .extract import Candidate

AZOOKEY_DEFAULTS_KEY = (
    "dev.ensan.inputmethod.azooKeyMac.preference.user_dictionary_temporal2"
)
AZOOKEY_PREFS = (
    Path.home()
    / "Library/Containers/dev.ensan.inputmethod.azooKeyMac/Data/Library"
    / "Preferences/dev.ensan.inputmethod.azooKeyMac.plist"
)

def stable_id(word: str, reading: str) -> str:
    """語と読みから決定的に UUID を作る。

    再実行しても同じ語には同じ id が付くので、既存辞書との突き合わせと
    重複排除が安定する。
    """
    digest = hashlib.sha1(f"{reading}\t{word}".encode()).digest()
    return str(uuid.UUID(bytes=digest[:16], version=5)).upper()


# --- macOS 標準 -----------------------------------------------------------


def write_macos_plist(cands: Sequence[Candidate], path: Path) -> int:
    items = [{"shortcut": c.reading, "phrase": c.word} for c in cands]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        plistlib.dump(items, fh, fmt=plistlib.FMT_XML, sort_keys=False)
    return len(items)


# --- azooKey --------------------------------------------------------------


def azookey_items(cands: Iterable[Candidate], hint: str = "") -> list[dict]:
    items = []
    for c in cands:
        item = {
            "word": c.word,
            "reading": c.reading,
            "id": stable_id(c.word, c.reading),
        }
        if hint:
            item["hint"] = hint
        items.append(item)
    return items


def write_azookey_json(
    cands: Sequence[Candidate], path: Path, hint: str = ""
) -> int:
    items = azookey_items(cands, hint)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(items)


def write_azookey_csv(
    cands: Sequence[Candidate], path: Path, hint: str = ""
) -> int:
    """azooKey の辞書取り込み画面向けの CSV。

    列順は UserDefaults 上の JSON スキーマ (word, reading, hint) に合わせる。
    取り込みが期待通りにならない場合は JSON を plist へ直接マージする
    `install-azookey` を使うこと。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        for c in cands:
            writer.writerow([c.word, c.reading, hint])
    return len(cands)


# --- レビュー用 TSV -------------------------------------------------------

TSV_HEADER = ["reading", "word", "count", "projects", "kind", "confidence"]


def write_review_tsv(cands: Sequence[Candidate], path: Path) -> int:
    """人が目視で刈り込むための一覧。不要な行を消して `build` に渡す。

    confidence=low は読みが文脈依存で揺れる形態素を含む語で、
    推定読みが誤っている可能性がある (例: 次セッション -> じせっしょん)。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(TSV_HEADER)
        for c in cands:
            writer.writerow(
                [c.reading, c.word, c.count, len(c.projects), c.kind, c.confidence]
            )
    return len(cands)


def read_review_tsv(path: Path) -> list[Candidate]:
    """レビュー後の TSV を読み戻す。`#` 始まりの行と空行は無視。"""
    out: list[Candidate] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if not row or not row[0].strip() or row[0].startswith("#"):
                continue
            if row[0] == "reading" and len(row) > 1 and row[1] == "word":
                continue  # ヘッダー行
            if len(row) < 2 or not row[1].strip():
                continue
            reading, word = row[0].strip(), row[1].strip()
            count = int(row[2]) if len(row) > 2 and row[2].isdigit() else 1
            kind = row[4].strip() if len(row) > 4 else "manual"
            out.append(Candidate(word, reading, kind, count))
    return out
