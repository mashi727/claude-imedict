"""Claude Code の対話履歴からユーザーが実際に書いた地の文を取り出す。

対象:
  ~/.claude/projects/<slug>/<session>.jsonl   会話トランスクリプト
  ~/.claude/history.jsonl                     プロンプト入力履歴 (打鍵そのもの)

ツール実行結果・添付ファイル・system-reminder・コードブロックなど、
ユーザーが書いたのではないテキストは辞書の語彙源として不適切なので除外する。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

DEFAULT_CLAUDE_DIR = Path.home() / ".claude"

# ユーザー由来でないテキスト塊
_RE_TAGGED_BLOCKS = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|"
    r"local-command-stdout|local-command-stderr|ide_selection|"
    r"user-prompt-submit-hook)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_RE_ORPHAN_TAG = re.compile(
    r"</?(system-reminder|command-name|command-message|command-args|"
    r"local-command-stdout|local-command-stderr|ide_selection)\b[^>]*>",
    re.IGNORECASE,
)
_RE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_RE_FENCE_OPEN = re.compile(r"```.*", re.DOTALL)
_RE_URL = re.compile(r"https?://\S+|www\.\S+")
# 日本語を含むパスも丸ごと落とせるよう、区切り記号以外を貪欲に取る
_RE_PATH = re.compile(r"(?:[~.]?/[^\s/、。「」『』()（）\[\]\"'`]+){2,}/?")
_RE_PLACEHOLDER = re.compile(
    r"\[(?:Pasted text|Image|Screenshot|Attached)[^\]]*\]", re.IGNORECASE
)
_RE_NOISE_LINE = re.compile(
    r"^\s*(?:Caveat: The messages below|\[Request interrupted"
    r"|This session is being continued|<local-command"
    r"|\[(?:INFO|WARN|WARNING|ERROR|DEBUG|STEP|TRACE|OK|NG|FAIL)\]"
    r"|Traceback \(most recent call last\)"
    r"|File \"|\s+File \")",
)
_RE_SLASH_CMD = re.compile(r"^/[a-zA-Z][\w:-]*\s*")
_RE_JA_CHAR = re.compile(r"[ぁ-ゟァ-ヺ々一-鿿]")


def clean_text(text: str, japanese_lines_only: bool = True) -> str:
    """辞書の語彙源として使える地の文だけを残す。

    japanese_lines_only=True のとき、日本語文字を一切含まない行を落とす。
    日本語話者のプロンプトにおいて全 ASCII の行はほぼ貼り付けたログ・
    コマンド・コード・パスであり、語彙源として有害なため。有用な英字語は
    日本語の文中にインラインで現れるので取りこぼさない。
    """
    if not text:
        return ""
    text = _RE_TAGGED_BLOCKS.sub(" ", text)
    text = _RE_ORPHAN_TAG.sub(" ", text)
    text = _RE_FENCE.sub(" ", text)
    text = _RE_FENCE_OPEN.sub(" ", text)  # 閉じ忘れフェンス以降を落とす
    text = _RE_PLACEHOLDER.sub(" ", text)
    text = _RE_URL.sub(" ", text)
    text = _RE_PATH.sub(" ", text)
    lines = []
    for ln in text.splitlines():
        if _RE_NOISE_LINE.match(ln):
            continue
        if japanese_lines_only and not _RE_JA_CHAR.search(ln):
            continue
        lines.append(ln)
    return "\n".join(lines)


@dataclass(slots=True)
class Utterance:
    text: str
    project: str
    role: str


def _project_label(cwd: str | None, fallback: str) -> str:
    if cwd:
        return cwd
    return fallback


def iter_transcripts(
    claude_dir: Path,
    include_assistant: bool = False,
    include_sidechain: bool = False,
    japanese_lines_only: bool = True,
) -> Iterator[Utterance]:
    """projects/*/*.jsonl から発話を取り出す。"""
    projects = claude_dir / "projects"
    if not projects.is_dir():
        return
    for path in sorted(projects.glob("*/*.jsonl")):
        slug = path.parent.name
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"type"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                rtype = rec.get("type")
                if rtype not in ("user", "assistant"):
                    continue
                if rtype == "assistant" and not include_assistant:
                    continue
                if rec.get("isSidechain") and not include_sidechain:
                    continue
                # isMeta はスキル本文・スラッシュコマンドの展開結果など、
                # user ロールで記録されるがユーザーが書いたのではないテキスト。
                # 量が非常に多く(実測でユーザー発話の3倍超)、放置すると
                # スキルの用語が辞書を占拠する。
                if rec.get("isMeta"):
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                project = _project_label(rec.get("cwd"), slug)
                for text in _message_texts(msg):
                    cleaned = clean_text(text, japanese_lines_only)
                    if cleaned.strip():
                        yield Utterance(cleaned, project, rtype)


def _message_texts(msg: dict) -> Iterator[str]:
    content = msg.get("content")
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            # tool_result / image / thinking はユーザーの記述ではない
            if isinstance(block, dict) and block.get("type") == "text":
                yield block.get("text") or ""


def iter_prompt_history(
    claude_dir: Path, japanese_lines_only: bool = True
) -> Iterator[Utterance]:
    """history.jsonl (プロンプト入力欄に打った文字列そのもの) を取り出す。"""
    path = claude_dir / "history.jsonl"
    if not path.is_file():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            display = rec.get("display") or ""
            display = _RE_SLASH_CMD.sub("", display)  # /cmd を落とし引数は残す
            cleaned = clean_text(display, japanese_lines_only)
            if cleaned.strip():
                yield Utterance(cleaned, rec.get("project") or "?", "user")


def collect(
    claude_dir: Path = DEFAULT_CLAUDE_DIR,
    include_assistant: bool = False,
    include_sidechain: bool = False,
    use_history: bool = True,
    japanese_lines_only: bool = True,
) -> Iterator[Utterance]:
    yield from iter_transcripts(
        claude_dir, include_assistant, include_sidechain, japanese_lines_only
    )
    if use_history:
        yield from iter_prompt_history(claude_dir, japanese_lines_only)
