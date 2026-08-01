import json
import plistlib

from claude_imedict import exporters, install
from claude_imedict.extract import Candidate


def _cands():
    return [
        Candidate("字幕ファイル", "じまくふぁいる", "kanji", 12),
        Candidate("LuaTeX", "luatex", "ascii", 8),
    ]


def test_macos_plist_uses_shortcut_and_phrase(tmp_path):
    path = tmp_path / "d.plist"
    exporters.write_macos_plist(_cands(), path)
    with path.open("rb") as fh:
        items = plistlib.load(fh)
    assert items[0] == {"shortcut": "じまくふぁいる", "phrase": "字幕ファイル"}
    assert items[1]["phrase"] == "LuaTeX"


def test_azookey_json_schema(tmp_path):
    path = tmp_path / "d.json"
    exporters.write_azookey_json(_cands(), path, hint="Claude")
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data["items"][0]
    assert set(item) == {"word", "reading", "id", "hint"}
    assert item["word"] == "字幕ファイル"
    assert item["reading"] == "じまくふぁいる"


def test_stable_id_is_deterministic():
    a = exporters.stable_id("字幕ファイル", "じまくふぁいる")
    b = exporters.stable_id("字幕ファイル", "じまくふぁいる")
    c = exporters.stable_id("字幕ファイル", "じまく")
    assert a == b != c


def test_review_tsv_roundtrip(tmp_path):
    path = tmp_path / "terms.tsv"
    exporters.write_review_tsv(_cands(), path)
    back = exporters.read_review_tsv(path)
    assert [(c.reading, c.word) for c in back] == [
        ("じまくふぁいる", "字幕ファイル"),
        ("luatex", "LuaTeX"),
    ]


def test_review_tsv_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "terms.tsv"
    path.write_text(
        "reading\tword\tcount\n"
        "# コメント行\n"
        "\n"
        "ほるん\tホルン\t9\n",
        encoding="utf-8",
    )
    back = exporters.read_review_tsv(path)
    assert [(c.reading, c.word) for c in back] == [("ほるん", "ホルン")]


def test_merge_into_azookey_preserves_existing_and_dedupes(tmp_path):
    prefs = tmp_path / "azookey.plist"
    existing = {
        "items": [{"word": "azooKey", "reading": "あずーきー", "id": "EXISTING"}]
    }
    with prefs.open("wb") as fh:
        plistlib.dump(
            {
                "someOtherSetting": True,
                exporters.AZOOKEY_DEFAULTS_KEY: json.dumps(
                    existing, ensure_ascii=False
                ),
            },
            fh,
        )

    cands = _cands() + [Candidate("azooKey", "あずーきー", "ascii", 3)]
    result = install.merge_into_azookey(cands, prefs_path=prefs, backup=False)

    assert result.added == 2
    assert result.skipped == 1
    assert result.total == 3

    with prefs.open("rb") as fh:
        written = plistlib.load(fh)
    assert written["someOtherSetting"] is True
    items = json.loads(written[exporters.AZOOKEY_DEFAULTS_KEY])["items"]
    assert items[0]["id"] == "EXISTING"
    assert {i["word"] for i in items} == {"azooKey", "字幕ファイル", "LuaTeX"}


def test_merge_dry_run_does_not_write(tmp_path):
    prefs = tmp_path / "azookey.plist"
    with prefs.open("wb") as fh:
        plistlib.dump({}, fh)
    before = prefs.read_bytes()
    result = install.merge_into_azookey(
        _cands(), prefs_path=prefs, backup=False, dry_run=True
    )
    assert result.added == 2
    assert prefs.read_bytes() == before


def test_merge_creates_backup(tmp_path):
    prefs = tmp_path / "azookey.plist"
    with prefs.open("wb") as fh:
        plistlib.dump({}, fh)
    result = install.merge_into_azookey(_cands(), prefs_path=prefs, backup=True)
    assert result.backup is not None and result.backup.is_file()
