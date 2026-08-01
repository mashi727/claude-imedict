"""claude-imedict のコマンドライン入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, exporters, extract, install, sources


def _eprint(*args, **kwargs) -> None:
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)


def _add_scan_options(p: argparse.ArgumentParser) -> None:
    src = p.add_argument_group("入力")
    src.add_argument(
        "--claude-dir",
        type=Path,
        default=sources.DEFAULT_CLAUDE_DIR,
        help="Claude Code のデータディレクトリ (既定: ~/.claude)",
    )
    src.add_argument(
        "--include-assistant",
        action="store_true",
        help="Claude 側の応答も語彙源に含める (既定はユーザー発話のみ)",
    )
    src.add_argument(
        "--include-sidechain",
        action="store_true",
        help="サブエージェントの発話も含める",
    )
    src.add_argument(
        "--no-history",
        action="store_true",
        help="~/.claude/history.jsonl (プロンプト入力履歴) を使わない",
    )
    src.add_argument(
        "--keep-ascii-lines",
        action="store_true",
        help="日本語を含まない行も語彙源にする (貼り付けログが混ざりやすい)",
    )

    flt = p.add_argument_group("抽出条件")
    flt.add_argument("--min-count", type=int, default=3, help="最低出現回数 (既定: 3)")
    flt.add_argument(
        "--min-projects", type=int, default=1, help="最低出現プロジェクト数 (既定: 1)"
    )
    flt.add_argument("--min-length", type=int, default=3, help="語の最短文字数 (既定: 3)")
    flt.add_argument("--max-length", type=int, default=24, help="語の最長文字数 (既定: 24)")
    flt.add_argument(
        "--max-span", type=int, default=3, help="複合語として連結する最大形態素数 (既定: 3)"
    )
    flt.add_argument("--limit", type=int, default=500, help="出力する語数の上限 (既定: 500)")
    flt.add_argument("--no-ascii", action="store_true", help="英字語を対象にしない")
    flt.add_argument("--no-japanese", action="store_true", help="日本語語を対象にしない")
    flt.add_argument(
        "--ascii-reading",
        choices=["lower", "letters", "both"],
        default="both",
        help="英字語の読み: lower=小文字綴り / letters=頭字語を一字ずつかな / both=両方",
    )
    flt.add_argument(
        "--exclude-existing",
        action="store_true",
        help="azooKey・macOS に既登録の語を除外する",
    )


def _build_config(args) -> extract.ExtractConfig:
    return extract.ExtractConfig(
        min_count=args.min_count,
        min_projects=args.min_projects,
        min_length=args.min_length,
        max_length=args.max_length,
        max_span_tokens=args.max_span,
        ascii_terms=not args.no_ascii,
        japanese_terms=not args.no_japanese,
        ascii_reading=args.ascii_reading,
    )


def _collect(args, quiet: bool = False):
    utts = []
    for utt in sources.collect(
        claude_dir=args.claude_dir,
        include_assistant=args.include_assistant,
        include_sidechain=args.include_sidechain,
        use_history=not args.no_history,
        japanese_lines_only=not args.keep_ascii_lines,
    ):
        utts.append(utt)
    if not quiet:
        chars = sum(len(u.text) for u in utts)
        projects = len({u.project for u in utts})
        _eprint(
            f"読み込み: 発話 {len(utts):,} 件 / {chars:,} 文字 / "
            f"{projects:,} プロジェクト"
        )
    if not utts:
        _eprint(
            f"警告: {args.claude_dir} に対話履歴が見つかりません。"
            " --claude-dir を確認してください。"
        )
    return utts


def _write_outputs(cands, out_dir: Path, hint: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv = out_dir / "terms.tsv"
    macos = out_dir / "macos-user-dictionary.plist"
    azoo_json = out_dir / "azookey-user-dictionary.json"
    azoo_csv = out_dir / "azookey-user-dictionary.csv"

    exporters.write_review_tsv(cands, tsv)
    exporters.write_macos_plist(cands, macos)
    exporters.write_azookey_json(cands, azoo_json, hint)
    exporters.write_azookey_csv(cands, azoo_csv, hint)

    print(f"{len(cands):,} 語を書き出しました。")
    print(f"  レビュー用 TSV   : {tsv}")
    print(f"  macOS 標準       : {macos}")
    print(f"  azooKey (JSON)   : {azoo_json}")
    print(f"  azooKey (CSV)    : {azoo_csv}")
    print()
    print("取り込み方:")
    print("  システム設定 > キーボード > テキスト入力 > テキスト置換 を開き、")
    print(f"  {macos.name} をリストへドラッグ&ドロップ。")
    print()
    print("  azooKey は macOS のユーザ辞書を自動で読み込むため、これだけで両方に反映されます。")
    print("  (azookey-user-dictionary.json / .csv は、OS と共有しない運用のための予備)")


def cmd_scan(args) -> int:
    utts = _collect(args)
    cfg = _build_config(args)

    def progress(i: int) -> None:
        if i:
            _eprint(f"  解析中 {i:,} 件...", end="\r")

    cands = extract.extract(utts, cfg, progress=progress)
    _eprint(" " * 40, end="\r")

    if args.exclude_existing:
        known = install.existing_azookey_pairs() | install.existing_macos_pairs()
        before = len(cands)
        cands = [c for c in cands if (c.reading, c.word) not in known]
        _eprint(f"既登録の除外: {before - len(cands)} 語")

    _eprint(f"候補語: {len(cands):,} 語 (上限 {args.limit:,} 語を出力)")
    cands = cands[: args.limit]
    _write_outputs(cands, args.out_dir, args.hint)
    return 0


def cmd_build(args) -> int:
    cands = exporters.read_review_tsv(args.tsv)
    if not cands:
        _eprint(f"エラー: {args.tsv} に有効な行がありません。")
        return 1
    _write_outputs(cands, args.out_dir, args.hint)
    return 0


def _load_candidates_for_install(args) -> list:
    if args.tsv:
        return exporters.read_review_tsv(args.tsv)
    import json

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    return [
        extract.Candidate(it["word"], it["reading"], "imported", 1)
        for it in data.get("items", [])
        if it.get("word") and it.get("reading")
    ]


def cmd_install_azookey(args) -> int:
    cands = _load_candidates_for_install(args)
    if not cands:
        _eprint("エラー: 登録する語がありません。")
        return 1

    if not args.i_know_azookey_follows_macos:
        _eprint(
            "azooKey は macOS のユーザ辞書 (テキスト置換) を自動で読み込みます。\n"
            "  macOS 側へ取り込めば azooKey にも反映されるため、通常このコマンドは不要です。\n"
            "  ここで書くと azooKey 独自辞書にも同じ語が入り、二重登録になります。\n\n"
            "  推奨: システム設定 > キーボード > テキスト入力 > テキスト置換 に\n"
            "        macos-user-dictionary.plist をドラッグ&ドロップ\n\n"
            "  azooKey にだけ入れたい語がある場合は --azookey-only を付けて再実行してください。"
        )
        return 1

    if not args.dry_run and install.azookey_running():
        if args.force_quit:
            _eprint("azooKey を終了しています...")
            if not install.quit_azookey():
                _eprint("エラー: azooKey を終了できませんでした。")
                return 1
        else:
            _eprint(
                "エラー: azooKey が動作中です。動作中に書き込むと "
                "終了時にメモリ上の内容で上書きされます。\n"
                "  入力ソースを他の IME に切り替えてから再実行するか、"
                "--force-quit を付けてください。"
            )
            return 1

    result = install.merge_into_azookey(
        cands, hint=args.hint, backup=not args.no_backup, dry_run=args.dry_run
    )
    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}追加 {result.added} 語 / 既存重複 {result.skipped} 語 / "
        f"辞書合計 {result.total} 語"
    )
    if result.backup:
        print(f"バックアップ: {result.backup}")
    if not args.dry_run:
        print("入力ソースを切り替え直すと反映されます。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-imedict",
        description="Claude Code の対話履歴から macOS 標準 / azooKey の"
        "ユーザー辞書を生成します。",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="履歴を解析して辞書ファイルを生成する")
    _add_scan_options(scan)
    scan.add_argument(
        "-o", "--out-dir", type=Path, default=Path("dict-out"), help="出力先ディレクトリ"
    )
    scan.add_argument("--hint", default="", help="azooKey エントリに付ける備考")
    scan.set_defaults(func=cmd_scan)

    build = sub.add_parser(
        "build", help="レビュー済み TSV から辞書ファイルを生成し直す"
    )
    build.add_argument("tsv", type=Path, help="terms.tsv (行を削って調整したもの)")
    build.add_argument(
        "-o", "--out-dir", type=Path, default=Path("dict-out"), help="出力先ディレクトリ"
    )
    build.add_argument("--hint", default="", help="azooKey エントリに付ける備考")
    build.set_defaults(func=cmd_build)

    inst = sub.add_parser(
        "install-azookey",
        help="azooKey 独自辞書へ直接マージする (通常不要: azooKey は macOS の辞書を自動追随)",
    )
    grp = inst.add_mutually_exclusive_group(required=True)
    grp.add_argument("--json", type=Path, help="azookey-user-dictionary.json")
    grp.add_argument("--tsv", type=Path, help="terms.tsv")
    inst.add_argument(
        "--azookey-only",
        dest="i_know_azookey_follows_macos",
        action="store_true",
        help="macOS と共有せず azooKey 独自辞書にだけ登録することを承知して実行する",
    )
    inst.add_argument("--hint", default="", help="エントリに付ける備考")
    inst.add_argument("--no-backup", action="store_true", help="plist を退避しない")
    inst.add_argument("--dry-run", action="store_true", help="書き込まず件数だけ表示")
    inst.add_argument(
        "--force-quit", action="store_true", help="動作中の azooKey を終了してから書き込む"
    )
    inst.set_defaults(func=cmd_install_azookey)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _eprint("\n中断しました。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
