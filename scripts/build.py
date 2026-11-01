#!/usr/bin/env python3
"""Build a static HTML reader from the Markdown sources. Requires Pandoc 3.x."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SERIES_FILE = ROOT / 'series.json'
STYLES = ROOT / 'site-src' / 'styles.css'
READER = 'markdown+pipe_tables+autolink_bare_uris-tex_math_dollars-smart'
SITE_INDEX_END = '<!-- SITE-INDEX-END'
LEADING_H1 = re.compile(r'\A# [^\n]*\n+')
MD_HREF = re.compile(r'href="([^"#?:]+\.md)((?:#[^"]*)?)"')


def load_series() -> dict:
    return json.loads(SERIES_FILE.read_text(encoding='utf-8'))


def site_index_text(text: str) -> str:
    """READMEのうち、サイトのトップページへ載せる範囲（マーカーより前）を返す。"""
    head, marker, _ = text.partition(SITE_INDEX_END)
    return head.rstrip() + '\n' if marker else text


def run_pandoc(text: str, args: list[str]) -> str:
    if not shutil.which('pandoc'):
        raise RuntimeError('Pandoc 3.x が必要である。guides/PUBLISHING.md を参照。')
    result = subprocess.run(['pandoc', *args], input=text, text=True, encoding='utf-8', capture_output=True, check=False)
    if result.returncode or result.stderr.strip():
        raise RuntimeError(f'Pandoc conversion failed: {result.stderr.strip()}')
    return result.stdout


def map_md_links(output: str) -> str:
    """相対の .md リンクを .html に直す。README.md はサイトのトップ index.html になる。"""
    def repl(m: re.Match) -> str:
        path = m.group(1)[:-3]
        if Path(path).name == 'README':
            path = path[:-len('README')] + 'index'
        return f'href="{path}.html{m.group(2)}"'
    return MD_HREF.sub(repl, output)


def wrap_tables(output: str) -> str:
    return output.replace('<table', '<div class="table-scroll"><table').replace('</table>', '</table></div>')


def render(text: str, *, drop_series_title: bool = False, shift: int = 0, prefix: str = '') -> str:
    if drop_series_title:
        text = LEADING_H1.sub('', text, count=1)
    args = ['--from', READER, '--to', 'html5', '--wrap=none', f'--shift-heading-level-by={shift}']
    if prefix:
        args += ['--id-prefix', prefix]
    return wrap_tables(map_md_links(run_pandoc(text, args)))


def page(series: dict, *, title: str, description: str, body: str, out_rel: Path, wide: bool = False) -> str:
    root = '../' * (len(out_rel.parts) - 1)
    site = html.escape(series['title'])
    body_class = ' class="wide"' if wide else ''
    return f'''<!doctype html>
<html lang="{series['language']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="stylesheet" href="{root}assets/styles.css">
</head>
<body{body_class}>
<a class="skip" href="#main">本文へ移動</a>
<header class="site-header">
<a class="site-name" href="{root}index.html">{site}</a>
<nav aria-label="サイト内">
<a href="{root}index.html">目次</a>
<a href="{root}complete.html">全文</a>
<a href="{root}{series['log'][:-3]}.html">検証ログ</a>
</nav>
</header>
<main id="main">
{body}
</main>
<footer class="site-footer">
<p>{site} ／ {html.escape(series['subtitle'])}</p>
<p><a href="{html.escape(series['repository'])}">GitHubリポジトリ</a> ／ ライセンス {html.escape(series['license'])}</p>
</footer>
</body>
</html>
'''


def chapter_nav(series: dict, index: int) -> str:
    chapters = series['chapters']
    parts = []
    if index > 0:
        p = chapters[index - 1]
        parts.append(f'<a rel="prev" href="{Path(p["path"]).stem}.html">← 第{p["number"]}回 {html.escape(p["title"])}</a>')
    parts.append('<a href="../index.html">目次</a>')
    if index + 1 < len(chapters):
        n = chapters[index + 1]
        parts.append(f'<a rel="next" href="{Path(n["path"]).stem}.html">第{n["number"]}回 {html.escape(n["title"])} →</a>')
    return '<nav class="chapter-nav" aria-label="前後の回">' + ''.join(parts) + '</nav>'


def build(out: Path) -> list[Path]:
    series = load_series()
    if out.exists():
        shutil.rmtree(out)
    (out / 'assets').mkdir(parents=True)
    shutil.copyfile(STYLES, out / 'assets' / 'styles.css')
    (out / '.nojekyll').write_text('', encoding='utf-8')
    written: list[Path] = []

    def emit(rel: str, content: str) -> None:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        written.append(target)

    index_md = site_index_text((ROOT / series['index']).read_text(encoding='utf-8'))
    emit('index.html', page(series, title=f'{series["title"]} ── {series["subtitle"]}', description=series['tagline'],
                            body=f'<article class="index">\n{render(index_md)}</article>', out_rel=Path('index.html'), wide=True))

    chapters = series['chapters']
    for i, c in enumerate(chapters):
        source = (ROOT / c['path']).read_text(encoding='utf-8')
        nav = chapter_nav(series, i)
        body = f'{nav}\n<article class="chapter">\n{render(source, drop_series_title=True, shift=-1)}</article>\n{nav}'
        rel = f'articles/{Path(c["path"]).stem}.html'
        emit(rel, page(series, title=f'第{c["number"]}回：{c["title"]} ｜ {series["title"]}', description=c['summary'],
                       body=body, out_rel=Path(rel)))

    sections = []
    for c in chapters:
        source = (ROOT / c['path']).read_text(encoding='utf-8')
        sections.append(f'<article class="chapter">\n{render(source, drop_series_title=True, prefix=f"ch{c["number"]}-")}</article>')
    toc = ''.join(f'<li><a href="#ch{c["number"]}-{c["slug"]}">第{c["number"]}回：{html.escape(c["title"])}</a></li>' for c in chapters)
    # 各回の h2 は Pandoc が見出し文字列から ID を作るため、目次用に別の ID を付けた区切りを置く。
    sections = [f'<div id="ch{c["number"]}-{c["slug"]}"></div>\n{s}' for c, s in zip(chapters, sections)]
    complete = f'<h1>{html.escape(series["title"])}　全{len(chapters)}回</h1>\n<nav class="toc" aria-label="全文の目次"><ol>{toc}</ol></nav>\n' + '\n<hr class="chapter-break">\n'.join(sections)
    emit('complete.html', page(series, title=f'全文 ｜ {series["title"]}', description=series['subtitle'], body=complete, out_rel=Path('complete.html')))

    log_rel = series['log'][:-3] + '.html'
    log_body = f'<article class="log">\n{render((ROOT / series["log"]).read_text(encoding="utf-8"))}</article>'
    emit(log_rel, page(series, title=f'検証ログ ｜ {series["title"]}', description='事実確認の対象、資料、結果、未解決事項の記録',
                       body=log_body, out_rel=Path(log_rel), wide=True))
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / '_site')
    args = parser.parse_args()
    written = build(args.out)
    print(f'Built {len(written)} pages into {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
