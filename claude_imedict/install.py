"""生成した辞書を azooKey (macOS) のユーザー辞書へ直接マージする。

azooKey のユーザー辞書は sandbox コンテナ内の UserDefaults に JSON 文字列
として保存されている。入力メソッドが起動中だとメモリ上の状態で上書き
されてしまうため、書き込み前にプロセスの生存を確認する。
"""

from __future__ import annotations

import json
import plistlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .exporters import AZOOKEY_DEFAULTS_KEY, AZOOKEY_PREFS, azookey_items
from .extract import Candidate

AZOOKEY_PROCESS = "azooKeyMac"


@dataclass(slots=True)
class MergeResult:
    added: int
    skipped: int
    total: int
    backup: Path | None


def azookey_running() -> bool:
    try:
        out = subprocess.run(
            ["/usr/bin/pgrep", "-x", AZOOKEY_PROCESS],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return out.returncode == 0


def quit_azookey() -> bool:
    """入力メソッドプロセスを終了させる (macOS が必要時に再起動する)。"""
    subprocess.run(
        ["/usr/bin/pkill", "-x", AZOOKEY_PROCESS], capture_output=True, check=False
    )
    for _ in range(20):
        if not azookey_running():
            return True
        time.sleep(0.25)
    return not azookey_running()


def _load_prefs(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return plistlib.load(fh)


def _existing_items(prefs: dict) -> list[dict]:
    raw = prefs.get(AZOOKEY_DEFAULTS_KEY)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    items = data.get("items")
    return items if isinstance(items, list) else []


def existing_azookey_pairs(prefs_path: Path = AZOOKEY_PREFS) -> set[tuple[str, str]]:
    """azooKey に既登録の (読み, 表記) の集合。"""
    return {
        (str(it.get("reading", "")), str(it.get("word", "")))
        for it in _existing_items(_load_prefs(prefs_path))
        if isinstance(it, dict) and it.get("word")
    }


def existing_macos_pairs() -> set[tuple[str, str]]:
    """macOS のテキスト置換に既登録の (読み, 表記) の集合。"""
    try:
        out = subprocess.run(
            ["/usr/bin/defaults", "export", "NSGlobalDomain", "-"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return set()
    if out.returncode != 0 or not out.stdout:
        return set()
    try:
        data = plistlib.loads(out.stdout)
    except Exception:
        return set()
    items = data.get("NSUserDictionaryReplacementItems") or []
    pairs = set()
    for it in items:
        if isinstance(it, dict) and it.get("with"):
            pairs.add((str(it.get("replace", "")), str(it["with"])))
    return pairs


def merge_into_azookey(
    cands: Sequence[Candidate],
    prefs_path: Path = AZOOKEY_PREFS,
    hint: str = "",
    backup: bool = True,
    dry_run: bool = False,
) -> MergeResult:
    """既存エントリを保持したまま候補語を追記する。

    同じ (読み, 表記) の組が既にあれば追加しない。
    """
    prefs = _load_prefs(prefs_path)
    existing = _existing_items(prefs)
    seen = {
        (str(it.get("reading", "")), str(it.get("word", "")))
        for it in existing
        if isinstance(it, dict)
    }

    added = []
    skipped = 0
    for item in azookey_items(cands, hint):
        if (item["reading"], item["word"]) in seen:
            skipped += 1
            continue
        seen.add((item["reading"], item["word"]))
        added.append(item)

    merged = existing + added
    backup_path = None
    if not dry_run:
        if backup and prefs_path.is_file():
            backup_path = prefs_path.with_suffix(
                prefs_path.suffix + f".bak-{int(time.time())}"
            )
            shutil.copy2(prefs_path, backup_path)
        prefs[AZOOKEY_DEFAULTS_KEY] = json.dumps(
            {"items": merged}, ensure_ascii=False
        )
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        with prefs_path.open("wb") as fh:
            plistlib.dump(prefs, fh, fmt=plistlib.FMT_BINARY)
        if prefs_path == AZOOKEY_PREFS:
            # cfprefsd は plist をキャッシュしている。実辞書を書き換えたときだけ
            # 再起動させ、書いた内容を読み直させる。
            subprocess.run(
                ["/usr/bin/killall", "-u", Path.home().name, "cfprefsd"],
                capture_output=True,
                check=False,
            )

    return MergeResult(len(added), skipped, len(merged), backup_path)
