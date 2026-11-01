#!/usr/bin/env python3
"""Validate the series: structure, headings, links, closing notes and unresolved markers."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE_INDEX_END = '<!-- SITE-INDEX-END'
GENERATED = {'complete.html'}  # build.py が生成するページ。原本には存在しない
UNRESOLVED = re.compile(r'<!--\s*要確認')
HEADING = re.compile(r'^(#{1,6}) +(.+?)\s*$')
FENCE = re.compile(r'^(```|~~~)')
LINK = re.compile(r'(?<!\!)\[[^\]]*\]\(([^)\s]+)\)')
NEXT_NOTE = re.compile(r'^\*次回：第(\d+)回「(.+?)」\*$', re.M)
BARE_URL = re.compile(r'https?://[A-Za-z0-9._~:/?#\[\]@!$&\'()*+,;=%-]+(?=[^\x00-\x7f])')


@dataclass
class Result:
    chapters: int = 0
    headings: int = 0
    links: int = 0


def headings(text: str) -> tuple[list[tuple[int, str]], bool]:
    """コードフェンス外の見出しを返す。2つ目はフェンスが閉じているか。"""
    found, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else HEADING.match(line)
        if m:
            found.append((len(m.group(1)), m.group(2)))
    return found, not fenced


def strip_code(text: str) -> str:
    return re.sub(r'^(```|~~~).*?^\1', '', text, flags=re.M | re.S)


def check_links(path: Path, text: str, errors: list[str], result: Result) -> None:
    for target in LINK.findall(strip_code(text)):
        result.links += 1
        if re.match(r'[a-z][a-z0-9+.-]*:', target) or target.startswith('#') or target in GENERATED:
            continue
        dest = (path.parent / target.split('#')[0]).resolve()
        if not dest.is_relative_to(ROOT) or not dest.exists():
            errors.append(f'{path.relative_to(ROOT)}: missing link target {target}')


def validate() -> tuple[Result, list[str]]:
    errors: list[str] = []
    result = Result()
    series = json.loads((ROOT / 'series.json').read_text(encoding='utf-8'))
    chapters = series['chapters']
    numbers = [c['number'] for c in chapters]
    if numbers != list(range(1, len(chapters) + 1)):
        errors.append('series.json: chapter numbers must be consecutive from 1')

    for i, c in enumerate(chapters):
        path = ROOT / c['path']
        if not path.exists():
            errors.append(f'{c["path"]}: file does not exist')
            continue
        result.chapters += 1
        text = path.read_text(encoding='utf-8')
        found, closed = headings(text)
        result.headings += len(found)
        if not closed:
            errors.append(f'{c["path"]}: unclosed code fence')
        if len(found) < 3 or found[0] != (1, series['title']):
            errors.append(f'{c["path"]}: first heading must be "# {series["title"]}"')
        elif found[1] != (2, f'第{c["number"]}回：{c["title"]}'):
            errors.append(f'{c["path"]}: second heading must be "## 第{c["number"]}回：{c["title"]}"')
        previous = 0
        for level, title in found:
            if level > previous + 1:
                errors.append(f'{c["path"]}: heading level jumps to {level} at "{title}"')
            previous = level
        if sum(1 for level, _ in found if level <= 2) != 2:
            errors.append(f'{c["path"]}: expected exactly one # and one ## heading')
        if UNRESOLVED.search(text):
            errors.append(f'{c["path"]}: unresolved 要確認 marker')
        for m in BARE_URL.finditer(text):
            errors.append(f'{c["path"]}: URL runs into Japanese text without a space: {m.group(0)[:60]}')
        notes = NEXT_NOTE.findall(text)
        if i + 1 < len(chapters):
            n = chapters[i + 1]
            if notes != [(str(n['number']), n['title'])]:
                errors.append(f'{c["path"]}: closing note must announce 第{n["number"]}回「{n["title"]}」')
        elif notes:
            errors.append(f'{c["path"]}: last chapter must not announce a next chapter')
        check_links(path, text, errors, result)

    readme = ROOT / series['index']
    log = ROOT / series['log']
    if not readme.exists() or not log.exists():
        errors.append('README.md or the verification log is missing')
        return result, errors
    index_text = readme.read_text(encoding='utf-8')
    if SITE_INDEX_END not in index_text:
        errors.append('README.md: missing SITE-INDEX-END marker')
    head = index_text.partition(SITE_INDEX_END)[0]
    for c in chapters:
        if f']({c["path"]})' not in head:
            errors.append(f'README.md: site index does not link {c["path"]}')
    if f']({series["log"]})' not in head:
        errors.append('README.md: site index does not link the verification log')
    for doc in (readme, log):
        text = doc.read_text(encoding='utf-8')
        check_links(doc, text, errors, result)
        if not headings(text)[1]:
            errors.append(f'{doc.relative_to(ROOT)}: unclosed code fence')
    return result, errors


def main() -> int:
    result, errors = validate()
    print(json.dumps({'chapters': result.chapters, 'headings': result.headings, 'links': result.links, 'errors': errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
