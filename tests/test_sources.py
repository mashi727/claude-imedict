import json

from claude_imedict import sources


def test_clean_text_strips_non_user_content():
    text = (
        "<system-reminder>これは無視される</system-reminder>\n"
        "この機能を実装してください。\n"
        "```python\nprint('コード内の日本語')\n```\n"
        "参考: https://example.com/日本語ページ\n"
        "[Pasted text #1 +92 lines]エラーを直して。\n"
        "[INFO] 起動完了\n"
    )
    out = sources.clean_text(text)
    assert "この機能を実装してください。" in out
    assert "エラーを直して。" in out
    assert "無視される" not in out
    assert "コード内の日本語" not in out
    assert "example.com" not in out
    assert "起動完了" not in out


def test_clean_text_drops_ascii_only_lines_by_default():
    text = "Traceback を貼ります。\n  File \"/tmp/a.py\", line 3\nValueError: bad\n"
    out = sources.clean_text(text)
    assert "貼ります" in out
    assert "ValueError" not in out
    # 明示的に許可すれば残る
    kept = sources.clean_text(text, japanese_lines_only=False)
    assert "ValueError" in kept


def test_clean_text_strips_paths_containing_japanese():
    text = "/Users/mashi/Dropbox/01_Projects/合宿資料/for_Download/a.mp4 を見て。\n"
    out = sources.clean_text(text)
    assert "Download" not in out
    assert "を見て。" in out


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def test_iter_transcripts_selects_user_text_only(tmp_path):
    proj = tmp_path / "projects" / "-Users-x-proj"
    proj.mkdir(parents=True)
    _write_jsonl(
        proj / "s.jsonl",
        [
            {"type": "user", "cwd": "/p", "message": {"role": "user",
             "content": "ホルン協奏曲の譜面を確認して。"}},
            {"type": "user", "cwd": "/p", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "ツール結果の日本語"},
                {"type": "text", "text": "字幕ファイルを作って。"},
            ]}},
            {"type": "assistant", "cwd": "/p", "message": {"role": "assistant",
             "content": [{"type": "text", "text": "応答の日本語"}]}},
            {"type": "user", "cwd": "/p", "isSidechain": True,
             "message": {"role": "user", "content": "サブエージェントの発話"}},
        ],
    )
    texts = [u.text for u in sources.iter_transcripts(tmp_path)]
    joined = "\n".join(texts)
    assert "ホルン協奏曲" in joined
    assert "字幕ファイル" in joined
    assert "ツール結果" not in joined
    assert "応答の日本語" not in joined
    assert "サブエージェント" not in joined

    with_assistant = "\n".join(
        u.text for u in sources.iter_transcripts(tmp_path, include_assistant=True)
    )
    assert "応答の日本語" in with_assistant


def test_iter_prompt_history_strips_slash_command(tmp_path):
    _write_jsonl(
        tmp_path / "history.jsonl",
        [{"display": "/luatex 演奏会プログラムを作成", "project": "/p"}],
    )
    texts = [u.text for u in sources.iter_prompt_history(tmp_path)]
    assert texts == ["演奏会プログラムを作成"]
