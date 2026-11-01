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
ILLUSTRATIONS = ROOT / 'assets' / 'illustrations'
READER = 'markdown+pipe_tables+autolink_bare_uris-tex_math_dollars-smart-implicit_figures'
SITE_INDEX_END = '<!-- SITE-INDEX-END'
LEADING_H1 = re.compile(r'\A# [^\n]*\n+')
MD_HREF = re.compile(r'href="([^"#?:]+\.md)((?:#[^"]*)?)"')
COVER = re.compile(r'<p><img src="(assets/illustrations/[^"]+)" alt="([^"]*)" ?/?></p>')
FIGURE = re.compile(r'<p><img src="([^"]+)" alt="([^"]*)" ?/?></p>\s*<p><em>(図\d+-\d+：.*?)</em></p>', re.S)
HEADING = re.compile(r'<h([23]) id="([^"]+)"[^>]*>(.*?)</h\1>', re.S)
TABLE = re.compile(r'<div class="table-scroll">(<table.*?</table>)</div>', re.S)
ROW = re.compile(r'<tr([^>]*)>(.*?)</tr>', re.S)
CELL = re.compile(r'<(t[hd])([^>]*)>(.*?)</\1>', re.S)

FILTERS = [('all', 'すべて'), ('confirmed', '確認済み'), ('fixed', '修正'), ('open', '未解決あり')]


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


def wrap_figures(output: str) -> str:
    """画像と直後の「図N-k：」キャプションを <figure> にまとめる。図はクリックで原寸を開ける。"""
    def repl(m: re.Match) -> str:
        src, alt, caption = m.groups()
        return (f'<figure><div class="figure-scroll"><a class="figure-link" href="{src}" title="図を原寸で開く">'
                f'<img src="{src}" alt="{alt}"></a></div><figcaption>{caption}</figcaption></figure>')
    def cover(m: re.Match) -> str:
        src, alt = m.groups()
        return (f'<figure class="cover"><div class="figure-scroll"><a class="figure-link" href="{src}" title="図を原寸で開く">'
                f'<img src="{src}" alt="{alt}"></a></div></figure>')
    return COVER.sub(cover, FIGURE.sub(repl, output))


def relocate_assets(output: str) -> str:
    """サイトのトップにある全文ページでは、原稿からの相対パス ../assets/ を assets/ に直す。"""
    return output.replace('"../assets/', '"assets/')


def render(text: str, *, drop_series_title: bool = False, shift: int = 0, prefix: str = '') -> str:
    if drop_series_title:
        text = LEADING_H1.sub('', text, count=1)
    args = ['--from', READER, '--to', 'html5', '--wrap=none', f'--shift-heading-level-by={shift}']
    if prefix:
        args += ['--id-prefix', prefix]
    return wrap_figures(wrap_tables(map_md_links(run_pandoc(text, args))))


def localize_chapter_links(output: str, chapters: list[dict]) -> str:
    """全文ページでは、他の回への相対リンク（NN-slug.html#節）を同じページ内のアンカーに直す。"""
    for c in chapters:
        stem = Path(c['path']).stem
        output = re.sub(rf'href="{re.escape(stem)}\.html#([^"]+)"', lambda m: f'href="#ch{c["number"]}-{m.group(1)}"', output)
    return output


def section_toc(body: str, level: int, summary: str) -> str:
    """本文中の見出し（level）から節目次を作る。見出しがなければ空文字。"""
    items = [(ident, title) for lv, ident, title in HEADING.findall(body) if int(lv) == level]
    if not items:
        return ''
    links = ''.join(f'<li><a href="#{ident}">{title}</a></li>' for ident, title in items)
    return f'<details class="toc"><summary>{summary}（{len(items)}節）</summary><ol>{links}</ol></details>'


def status_note(chapter: dict) -> str:
    status = chapter.get('status')
    if not status:
        return ''
    return f'<aside class="status" role="note"><strong>{html.escape(status["label"])}</strong>{html.escape(status["text"])}</aside>'


def decorate_chapter(body: str, chapter: dict, *, title_tag: str, section_level: int) -> str:
    """回のタイトル直後に状態ラベルと節目次を差し込む。"""
    close = f'</{title_tag}>'
    head, sep, rest = body.partition(close)
    if not sep:
        raise ValueError(f'{chapter["path"]}: title heading not found')
    extra = status_note(chapter) + section_toc(rest, section_level, 'この回の節')
    return f'{head}{close}\n{extra}{rest}'


def text_of(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', fragment))).strip()


def row_kinds(result: str, remaining: str) -> list[str]:
    """検証ログの1行を「確認結果」と「残課題」の文面から分類する。"""
    kinds = []
    if result.startswith('確認済み'):
        kinds.append('confirmed')
    if result.startswith('修正') or result.startswith('確認済みと修正'):
        kinds.append('fixed')
    if remaining not in ('', 'なし'):
        kinds.append('open')
    return kinds


def annotate_log_tables(output: str) -> str:
    """検証ログの表に data-label（スマホのカード表示用）と data-kinds（絞り込み用）を付ける。
    行ごとの区分に加え、表全体の区分を表の外側（.table-scroll）にも持たせ、該当行のない表を隠せるようにする。"""
    def table_repl(m: re.Match) -> str:
        table = m.group(1)
        header: list[str] = []
        is_case_table = False
        table_kinds: list[str] = []

        def row_repl(r: re.Match) -> str:
            nonlocal header, is_case_table
            attrs, inner = r.group(1), r.group(2)
            cells = CELL.findall(inner)
            if cells and cells[0][0] == 'th':
                header = [text_of(c[2]) for c in cells]
                is_case_table = '確認結果' in header and '残課題' in header
                return r.group(0)
            index = iter(range(len(header)))

            def cell_repl(c: re.Match) -> str:
                i = next(index, None)
                label = f' data-label="{html.escape(header[i])}"' if i is not None else ''
                return f'<td{c.group(2)}{label}>{c.group(3)}</td>'
            new_inner = CELL.sub(cell_repl, inner)
            if is_case_table:
                values = {header[i]: text_of(c[2]) for i, c in enumerate(cells) if i < len(header)}
                kinds = row_kinds(values.get('確認結果', ''), values.get('残課題', ''))
                table_kinds.extend(k for k in kinds if k not in table_kinds)
                attrs += f' data-kinds="{" ".join(kinds)}"'
            return f'<tr{attrs}>{new_inner}</tr>'

        annotated = ROW.sub(row_repl, table)
        wrapper = f' data-cases data-kinds="{" ".join(table_kinds)}"' if is_case_table else ''
        return f'<div class="table-scroll"{wrapper}>{annotated}</div>'
    return TABLE.sub(table_repl, output)


def log_filter_bar() -> str:
    inputs = ''.join(
        f'<input type="radio" name="log-filter" id="f-{key}"{" checked" if key == "all" else ""}>'
        f'<label for="f-{key}">{label}</label>' for key, label in FILTERS)
    return f'<fieldset class="log-filter"><legend>区分で絞り込む</legend>{inputs}</fieldset>\n'


def add_log_filter(output: str) -> str:
    marker = '<h2 id="第1回"'
    return output.replace(marker, log_filter_bar() + marker, 1)


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
    shutil.copytree(ILLUSTRATIONS, out / 'assets' / 'illustrations')
    (out / '.nojekyll').write_text('', encoding='utf-8')
    written: list[Path] = []
    log_page = series['log'][:-3] + '.html'

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
        article = decorate_chapter(render(source, drop_series_title=True, shift=-1), c, title_tag='h1', section_level=2)
        rel = f'articles/{Path(c["path"]).stem}.html'
        emit(rel, page(series, title=f'第{c["number"]}回：{c["title"]} ｜ {series["title"]}', description=c['summary'],
                       body=f'{nav}\n<article class="chapter">\n{article}</article>\n{nav}', out_rel=Path(rel)))

    sections, toc_items = [], []
    for c in chapters:
        source = (ROOT / c['path']).read_text(encoding='utf-8')
        prefix = f'ch{c["number"]}-'
        article = decorate_chapter(relocate_assets(localize_chapter_links(render(source, drop_series_title=True, prefix=prefix), chapters)),
                                   c, title_tag='h2', section_level=3)
        title_id = HEADING.search(article).group(2)
        sections.append(f'<article class="chapter">\n{article}</article>')
        toc_items.append(f'<li><a href="#{title_id}">第{c["number"]}回：{html.escape(c["title"])}</a></li>')
    complete = (f'<h1>{html.escape(series["title"])}　全{len(chapters)}回</h1>\n'
                f'<nav class="toc" aria-label="全文の目次"><ol>{"".join(toc_items)}</ol></nav>\n'
                + '\n<hr class="chapter-break">\n'.join(sections))
    emit('complete.html', page(series, title=f'全文 ｜ {series["title"]}', description=series['subtitle'], body=complete,
                               out_rel=Path('complete.html')))

    log_html = add_log_filter(annotate_log_tables(render((ROOT / series['log']).read_text(encoding='utf-8'))))
    emit(log_page, page(series, title=f'検証ログ ｜ {series["title"]}', description='事実確認の対象、資料、結果、未解決事項の記録',
                        body=f'<article class="log">\n{log_html}</article>', out_rel=Path(log_page), wide=True))
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
