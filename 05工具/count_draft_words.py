#!/usr/bin/env python3
"""Count draft chapter length for the novel project."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_DRAFT_DIR = Path("03正文草稿")
DEFAULT_MIN_TARGET = 3000
DEFAULT_IDEAL_MAX_TARGET = 3500
DEFAULT_MAX_TARGET = 4000

CHAPTER_FILE_RE = re.compile(r"^(?P<num>\d{3})_(?P<name>.+)\.md$")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-_'][A-Za-z0-9]+)*")
NON_SPACE_RE = re.compile(r"\S")


@dataclass(frozen=True)
class ChapterStats:
    volume: str
    chapter_no: int
    title: str
    word_count: int
    visible_chars: int
    cjk_chars: int
    ascii_words: int
    status: str
    path: str


def project_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def iter_chapter_files(draft_dir: Path, include_000: bool) -> Iterable[Path]:
    for path in sorted(draft_dir.rglob("*.md")):
        match = CHAPTER_FILE_RE.match(path.name)
        if not match:
            continue
        if not include_000 and match.group("num") == "000":
            continue
        yield path


def strip_count_ignored_markdown(text: str) -> tuple[str, str | None]:
    title: str | None = None
    kept_lines: list[str] = []
    in_fenced_code = False

    for raw_line in text.replace("\ufeff", "").splitlines():
        line = raw_line.rstrip("\n")

        if line.strip().startswith("```"):
            in_fenced_code = not in_fenced_code
            continue
        if in_fenced_code:
            continue

        if HEADING_RE.match(line):
            if title is None:
                title = HEADING_RE.sub("", line).strip()
            continue

        kept_lines.append(line)

    return "\n".join(kept_lines), title


def chapter_title_from_filename(path: Path) -> str:
    match = CHAPTER_FILE_RE.match(path.name)
    if not match:
        return path.stem
    return match.group("name")


def clean_title(markdown_title: str | None, path: Path) -> str:
    title = markdown_title or chapter_title_from_filename(path)
    title = re.sub(r"^第\s*\d+\s*章[：:]\s*", "", title)
    return title.strip() or chapter_title_from_filename(path)


def status_for_count(count: int, min_target: int, ideal_max: int, max_target: int) -> str:
    if count < min_target:
        return "偏短"
    if count <= ideal_max:
        return "达标"
    if count <= max_target:
        return "可接受"
    return "偏长"


def target_label(min_target: int, ideal_max: int, max_target: int) -> str:
    if ideal_max >= max_target:
        return f"{min_target}-{max_target}"
    return f"{min_target}-{ideal_max}，{ideal_max + 1}-{max_target} 可接受"


def count_chapter(
    path: Path,
    root: Path,
    min_target: int,
    ideal_max: int,
    max_target: int,
) -> ChapterStats:
    raw = path.read_text(encoding="utf-8")
    body, markdown_title = strip_count_ignored_markdown(raw)

    cjk_chars = len(CJK_RE.findall(body))
    ascii_words = len(ASCII_WORD_RE.findall(CJK_RE.sub(" ", body)))
    visible_chars = len(NON_SPACE_RE.findall(body))
    word_count = cjk_chars + ascii_words

    match = CHAPTER_FILE_RE.match(path.name)
    chapter_no = int(match.group("num")) if match else -1

    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path

    return ChapterStats(
        volume=path.parent.name,
        chapter_no=chapter_no,
        title=clean_title(markdown_title, path),
        word_count=word_count,
        visible_chars=visible_chars,
        cjk_chars=cjk_chars,
        ascii_words=ascii_words,
        status=status_for_count(word_count, min_target, ideal_max, max_target),
        path=rel.as_posix(),
    )


def render_table(rows: list[ChapterStats]) -> str:
    lines = [
        "| 卷 | 章 | 标题 | 正文字数 | 含标点字符 | 状态 | 文件 |",
        "|---|---:|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.volume} | {row.chapter_no:03d} | {row.title} | "
            f"{row.word_count} | {row.visible_chars} | {row.status} | `{row.path}` |"
        )
    return "\n".join(lines)


def render_summary(rows: list[ChapterStats]) -> str:
    total_words = sum(row.word_count for row in rows)
    total_visible = sum(row.visible_chars for row in rows)
    count = len(rows)
    average = round(total_words / count) if count else 0
    return (
        f"章节数: {count}\n"
        f"正文字数合计: {total_words}\n"
        f"含标点字符合计: {total_visible}\n"
        f"平均正文字数: {average}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计正文草稿章节字数。")
    parser.add_argument(
        "--draft-dir",
        type=Path,
        default=DEFAULT_DRAFT_DIR,
        help="正文草稿目录，默认：03正文草稿",
    )
    parser.add_argument(
        "--min",
        dest="min_target",
        type=int,
        default=DEFAULT_MIN_TARGET,
        help="单章目标下限，默认：3000",
    )
    parser.add_argument(
        "--ideal-max",
        dest="ideal_max_target",
        type=int,
        default=DEFAULT_IDEAL_MAX_TARGET,
        help="单章理想目标上限，默认：3500",
    )
    parser.add_argument(
        "--max",
        dest="max_target",
        type=int,
        default=DEFAULT_MAX_TARGET,
        help="单章可接受上限，默认：4000",
    )
    parser.add_argument(
        "--include-000",
        action="store_true",
        help="包含 000_ 开头的说明文件；默认不统计。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON，便于后续自动化处理。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.ideal_max_target > args.max_target:
        raise SystemExit("--ideal-max 不能大于 --max")

    root = project_root_from_script()
    draft_dir = args.draft_dir
    if not draft_dir.is_absolute():
        draft_dir = root / draft_dir

    if not draft_dir.exists():
        raise SystemExit(f"正文目录不存在: {draft_dir}")

    rows = [
        count_chapter(path, root, args.min_target, args.ideal_max_target, args.max_target)
        for path in iter_chapter_files(draft_dir, args.include_000)
    ]

    if args.json:
        payload = {
            "draft_dir": draft_dir.relative_to(root).as_posix()
            if draft_dir.is_relative_to(root)
            else draft_dir.as_posix(),
            "target": {
                "min": args.min_target,
                "ideal_max": args.ideal_max_target,
                "max": args.max_target,
            },
            "summary": {
                "chapters": len(rows),
                "word_count": sum(row.word_count for row in rows),
                "visible_chars": sum(row.visible_chars for row in rows),
            },
            "chapters": [asdict(row) for row in rows],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"统计范围: {draft_dir.relative_to(root).as_posix() if draft_dir.is_relative_to(root) else draft_dir}")
    print(
        "单章目标: "
        f"{target_label(args.min_target, args.ideal_max_target, args.max_target)} 正文字数\n"
    )
    print(render_table(rows))
    print()
    print(render_summary(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
