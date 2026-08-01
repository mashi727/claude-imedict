from claude_imedict import kana


def test_romaji_to_hiragana_basic():
    assert kana.romaji_to_hiragana("kyousou") == "きょうそう"
    assert kana.romaji_to_hiragana("gakushuu") == "がくしゅう"
    assert kana.romaji_to_hiragana("keitarou") == "けいたろう"
    assert kana.romaji_to_hiragana("shiryou") == "しりょう"


def test_romaji_to_hiragana_sokuon_and_hatsuon():
    assert kana.romaji_to_hiragana("gasshuku") == "がっしゅく"
    assert kana.romaji_to_hiragana("kinyuu") == "きにゅう"
    assert kana.romaji_to_hiragana("hon") == "ほん"
    assert kana.romaji_to_hiragana("sesshon") == "せっしょん"


def test_romaji_to_hiragana_icu_notations():
    # ICU は小書き仮名を "~" 前置、四つ仮名を dz で綴る
    assert kana.romaji_to_hiragana("okona~tsu") == "おこなっ"
    assert kana.romaji_to_hiragana("hidzuke") == "ひづけ"


def test_romaji_to_hiragana_rejects_non_japanese():
    # 中国語読みへのフォールバック等は読みとして採用しない
    assert kana.romaji_to_hiragana("2rén") is None
    assert kana.romaji_to_hiragana("") is None


def test_kana_conversion():
    assert kana.katakana_to_hiragana("チャプター") == "ちゃぷたー"
    assert kana.hiragana_to_katakana("ほるん") == "ホルン"


def test_acronym_reading():
    assert kana.acronym_reading("URL") == "ゆーあーるえる"
    assert kana.acronym_reading("PDF") == "ぴーでぃーえふ"
    assert kana.acronym_reading("MP3") == "えむぴーさん"
    # 全大文字でないものや長すぎるものは対象外
    assert kana.acronym_reading("LuaTeX") is None
    assert kana.acronym_reading("A") is None


def test_character_class_helpers():
    assert kana.is_katakana("チャプター")
    assert not kana.is_katakana("チャプタ名")
    assert kana.has_kanji("字幕ファイル")
    assert kana.is_ascii_word("PySide6")
    assert not kana.is_ascii_word("6PySide")
