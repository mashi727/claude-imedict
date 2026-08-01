from claude_imedict import extract
from claude_imedict.sources import Utterance


def _utts(text: str, times: int = 5, project: str = "p1"):
    return [Utterance(text, project, "user") for _ in range(times)]


def test_extracts_compound_noun_with_reading():
    cands = extract.extract(
        _utts("字幕ファイルを作成してください。"),
        extract.ExtractConfig(min_count=3),
    )
    by_word = {c.word: c for c in cands}
    assert "字幕ファイル" in by_word
    assert by_word["字幕ファイル"].reading == "じまくふぁいる"


def test_drops_subspan_that_never_stands_alone():
    # 「一次資料」しか現れないなら「次資料」は登録しない
    cands = extract.extract(
        _utts("一次資料にあたって確認する。", times=10),
        extract.ExtractConfig(min_count=3),
    )
    words = {c.word for c in cands}
    assert "一次資料" in words
    assert "次資料" not in words


def test_rejects_inflected_single_token():
    cands = extract.extract(
        _utts("その処理を行なった結果を教えて。", times=10),
        extract.ExtractConfig(min_count=3, min_length=2),
    )
    assert not any(c.word.endswith("っ") for c in cands)


def test_ascii_casing_prefers_internal_capitals():
    utts = _utts("Luatex で組版する。", times=5) + _utts("LuaTeX で組版する。", times=4)
    cands = extract.extract(utts, extract.ExtractConfig(min_count=3))
    ascii_words = {c.word for c in cands if c.kind == "ascii"}
    assert "LuaTeX" in ascii_words
    assert "Luatex" not in ascii_words


def test_ascii_all_lowercase_is_not_registered():
    # 読みと表記が一致する語は登録しても意味がない
    cands = extract.extract(_utts("ffmpeg で変換する。", times=8))
    assert not any(c.word == "ffmpeg" for c in cands)


def test_acronym_gets_both_readings():
    cands = extract.extract(
        _utts("SRT を書き出して。", times=8),
        extract.ExtractConfig(min_count=3, ascii_reading="both"),
    )
    readings = {c.reading for c in cands if c.word == "SRT"}
    assert readings == {"srt", "えすあーるてぃー"}


def test_min_projects_filters_single_project_terms():
    utts = _utts("スペクトログラムを表示する。", times=10, project="only")
    assert any(c.word == "スペクトログラム" for c in extract.extract(utts))
    filtered = extract.extract(utts, extract.ExtractConfig(min_projects=2))
    assert not any(c.word == "スペクトログラム" for c in filtered)


def test_common_words_are_excluded():
    cands = extract.extract(_utts("設定を確認して修正してください。", times=10))
    words = {c.word for c in cands}
    assert "設定" not in words
    assert "確認" not in words


def test_ambiguous_reading_is_flagged_low_confidence():
    utts = _utts("次セッションに引き継ぐ。", times=6) + _utts("次の資料を見る。", times=6)
    cands = extract.extract(utts, extract.ExtractConfig(min_count=3))
    target = [c for c in cands if c.word == "次セッション"]
    assert target and target[0].confidence == "low"


def test_known_brand_uses_canonical_spelling():
    # ユーザーの打鍵が Github に偏っていても、辞書には GitHub を登録する
    utts = _utts("Github にプッシュする。", times=9)
    cands = extract.extract(utts, extract.ExtractConfig(min_count=3))
    ascii_words = {c.word for c in cands if c.kind == "ascii"}
    assert "GitHub" in ascii_words
    assert "Github" not in ascii_words
