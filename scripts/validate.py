#!/usr/bin/env python3
"""Validate the series: structure, headings, links, figures, closing notes and unresolved markers."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE_INDEX_END = '<!-- SITE-INDEX-END'
GENERATED = {'complete.html'}  # build.py が生成するページ。原本には存在しない
UNRESOLVED = re.compile(r'<!--\s*要確認')
HEADING = re.compile(r'^(#{1,6}) +(.+?)\s*$')
FENCE = re.compile(r'^(```|~~~)')
LINK = re.compile(r'(?<!\!)\[[^\]]*\]\(([^)\s]+)\)')
NEXT_NOTE = re.compile(r'^\*次回：第(\d+)回「(.+?)」\*$', re.M)
BARE_URL = re.compile(r'https?://[A-Za-z0-9._~:/?#\[\]@!$&\'()*+,;=%-]+(?=[^\x00-\x7f])')
FIGURE_DIR = 'assets/illustrations'
VIGNETTE_DIR = 'assets/vignettes'
FIGURE_REF = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)\)[ \t]*$', re.M)
VIGNETTE_REF = re.compile(r'^!\[\]\(([^)\s]+)\)[ \t]*$', re.M)
FIGURE_WITH_CAPTION = re.compile(r'^!\[[^\]]*\]\([^)\s]+\)[ \t]*\n\n\*図(\d+)-(\d+)：.+\*[ \t]*$', re.M)
SVG_FORBIDDEN = {'script', 'foreignObject', 'image', 'iframe', 'style', 'a'}
SVG_MIN_FONT = 14


@dataclass
class Result:
    chapters: int = 0
    headings: int = 0
    links: int = 0
    figures: int = 0
    vignettes: int = 0
    svg_files: int = 0


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
    titles = {title for _, title in headings(text)[0]}
    for target in LINK.findall(strip_code(text)):
        result.links += 1
        if target.startswith('#'):
            if target[1:] not in titles:
                errors.append(f'{path.relative_to(ROOT)}: no heading for in-page link {target}')
            continue
        if re.match(r'[a-z][a-z0-9+.-]*:', target) or target in GENERATED:
            continue
        dest = (path.parent / target.split('#')[0]).resolve()
        if not dest.is_relative_to(ROOT) or not dest.exists():
            errors.append(f'{path.relative_to(ROOT)}: missing link target {target}')


def svg_errors(path: Path) -> list[str]:
    """図のSVGが、自己完結で受動的（スクリプト・外部参照なし）かを検査する。"""
    name = path.name
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f'{name}: SVG parse error: {exc}']
    local = lambda el: el.tag.rsplit('}', 1)[-1]  # noqa: E731
    errors = []
    if local(root) != 'svg':
        return [f'{name}: root element must be svg']
    if not root.get('viewBox'):
        errors.append(f'{name}: missing viewBox')
    if root.get('role') != 'img':
        errors.append(f'{name}: svg must have role="img"')
    children = {local(el) for el in root.iter()}
    for needed in ('title', 'desc'):
        if needed not in children:
            errors.append(f'{name}: missing <{needed}>')
    for el in root.iter():
        tag = local(el)
        if tag in SVG_FORBIDDEN:
            errors.append(f'{name}: forbidden SVG element <{tag}>')
        for attr, value in el.attrib.items():
            key = attr.rsplit('}', 1)[-1]
            if key.lower().startswith('on'):
                errors.append(f'{name}: event handler attribute {key}')
            if key == 'href' or 'url(http' in value or value.strip().startswith(('http:', 'https:', '//')):
                errors.append(f'{name}: external reference in {key}')
        size = el.get('font-size')
        if size and float(size) < SVG_MIN_FONT:
            errors.append(f'{name}: font-size {size} is below {SVG_MIN_FONT}px')
    return errors


def check_figures(chapter: dict, text: str, errors: list[str], result: Result) -> None:
    """本文のSVG参照・キャプションと series.json の figures を突き合わせる。"""
    figures = chapter.get('figures', [])
    body = strip_code(text)
    refs = [(alt, target) for alt, target in FIGURE_REF.findall(body) if target.startswith(f'../{FIGURE_DIR}/')]
    result.figures += len(refs)
    path = chapter['path']
    if [target for _, target in refs] != [f'../{FIGURE_DIR}/{name}' for name in figures]:
        errors.append(f'{path}: figure references must match series.json figures, in order')
    for alt, target in refs:
        if not alt.strip():
            errors.append(f'{path}: missing alt text for {target}')
        if not (ROOT / path).parent.joinpath(target).resolve().exists():
            errors.append(f'{path}: missing figure file {target}')
    captions = [(int(a), int(b)) for a, b in FIGURE_WITH_CAPTION.findall(body)]
    if captions != [(chapter['number'], i) for i in range(1, len(figures) + 1)]:
        errors.append(f'{path}: each figure must be followed by a caption 図{chapter["number"]}-1 .. 図{chapter["number"]}-{len(figures)} in order')


def check_vignettes(chapter: dict, text: str, errors: list[str], result: Result) -> None:
    """文字を持たない装飾の線画（ひとこま）の参照を、series.json の vignettes と突き合わせる。"""
    path = chapter['path']
    body = strip_code(text)
    refs = [t for t in VIGNETTE_REF.findall(body) if t.startswith(f'../{VIGNETTE_DIR}/')]
    result.vignettes += len(refs)
    if refs != [f'../{VIGNETTE_DIR}/{name}' for name in chapter.get('vignettes', [])]:
        errors.append(f'{path}: vignette references must match series.json vignettes, in order')
    for target in refs:
        if not (ROOT / path).parent.joinpath(target).resolve().exists():
            errors.append(f'{path}: missing vignette file {target}')
    stray = [t for t in VIGNETTE_REF.findall(body) if not t.startswith(f'../{VIGNETTE_DIR}/')]
    if stray:
        errors.append(f'{path}: an image with no alt text must be a vignette in {VIGNETTE_DIR}/: {stray[0]}')


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
        note = NEXT_NOTE.search(text)
        reference = re.search(r'^### 参考文献\s*$', text, re.M)
        if note and reference and reference.start() > note.start():
            errors.append(f'{c["path"]}: 参考文献 must come before the closing 次回 note')
        notes = NEXT_NOTE.findall(text)
        if i + 1 < len(chapters):
            n = chapters[i + 1]
            if notes != [(str(n['number']), n['title'])]:
                errors.append(f'{c["path"]}: closing note must announce 第{n["number"]}回「{n["title"]}」')
        elif notes:
            errors.append(f'{c["path"]}: last chapter must not announce a next chapter')
        check_links(path, text, errors, result)
        check_figures(c, text, errors, result)
        check_vignettes(c, text, errors, result)

    listed = {name for c in chapters for name in c.get('figures', [])}
    cover = series.get('cover', '')
    if cover:
        if Path(cover).parent.as_posix() != FIGURE_DIR:
            errors.append(f'series.json: cover must be in {FIGURE_DIR}/')
        listed.add(Path(cover).name)
    figure_dir = ROOT / FIGURE_DIR
    found = {p.name for p in figure_dir.glob('*.svg')} if figure_dir.exists() else set()
    for name in sorted(listed - found):
        errors.append(f'{FIGURE_DIR}/{name}: listed in series.json but missing')
    for name in sorted(found - listed):
        errors.append(f'{FIGURE_DIR}/{name}: not listed in series.json')
    if sum(len(c.get('figures', [])) for c in chapters) + (1 if cover else 0) != len(listed):
        errors.append('series.json: a figure is listed more than once')
    vignettes = [name for c in chapters for name in c.get('vignettes', [])]
    vignette_dir = ROOT / VIGNETTE_DIR
    vignette_found = {p.name for p in vignette_dir.glob('*.svg')} if vignette_dir.exists() else set()
    if len(vignettes) != len(set(vignettes)):
        errors.append('series.json: a vignette is listed more than once')
    for name in sorted(set(vignettes) - vignette_found):
        errors.append(f'{VIGNETTE_DIR}/{name}: listed in series.json but missing')
    for name in sorted(vignette_found - set(vignettes)):
        errors.append(f'{VIGNETTE_DIR}/{name}: not listed in series.json')
    for name in sorted(vignette_found & set(vignettes)):
        result.svg_files += 1
        errors += svg_errors(vignette_dir / name)
        if '<text' in (vignette_dir / name).read_text(encoding='utf-8'):
            errors.append(f'{VIGNETTE_DIR}/{name}: a vignette must not contain text')
    for name in sorted(found & listed):
        result.svg_files += 1
        errors += svg_errors(figure_dir / name)

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
    if cover and not re.search(rf'^!\[[^\]]+\]\({re.escape(cover)}\)\s*$', head, re.M):
        errors.append(f'README.md: the site index must show the cover {cover} with alt text')
    if f']({series["log"]})' in head:
        errors.append('README.md: the site index must not link the verification log')
    if f']({series["log"]})' not in index_text:
        errors.append('README.md: the repository section must link the verification log')
    for doc in (readme, log):
        text = doc.read_text(encoding='utf-8')
        check_links(doc, text, errors, result)
        if not headings(text)[1]:
            errors.append(f'{doc.relative_to(ROOT)}: unclosed code fence')
    return result, errors


def main() -> int:
    result, errors = validate()
    print(json.dumps({'chapters': result.chapters, 'headings': result.headings, 'links': result.links,
                      'figures': result.figures, 'vignettes': result.vignettes, 'svg_files': result.svg_files, 'errors': errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
