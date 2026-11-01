from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import draw_figures  # noqa: E402
from build import (annotate_log_tables, build, load_series, localize_chapter_links, map_md_links, relocate_assets,  # noqa: E402
                   row_kinds, section_toc, site_index_text, status_note, wrap_figures, wrap_tables)
from check_html import check  # noqa: E402
from validate import BARE_URL, Result, check_figures, headings, svg_errors, validate  # noqa: E402


class RepositoryTests(unittest.TestCase):
    def test_repository_is_valid(self):
        result, errors = validate()
        self.assertEqual(errors, [])
        self.assertEqual(result.chapters, len(load_series()['chapters']))

    def test_built_site_passes_html_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build(out)
            report = check(out)
            self.assertEqual(report['errors'], [])
            self.assertEqual(report['html_pages'], len(load_series()['chapters']) + 3)

    def test_built_pages_contain_no_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build(out)
            for page in out.rglob('*.html'):
                text = page.read_text(encoding='utf-8')
                self.assertNotIn('<script', text, page.name)
                self.assertNotIn('src="http', text, page.name)
            self.assertTrue((out / 'index.html').read_text(encoding='utf-8').count('articles/') >= 4)

    def test_md_links_become_html(self):
        self.assertEqual(map_md_links('<a href="articles/01-a.md#x">'), '<a href="articles/01-a.html#x">')
        self.assertEqual(map_md_links('<a href="../README.md">'), '<a href="../index.html">')
        self.assertEqual(map_md_links('<a href="https://example.com/a.md">'), '<a href="https://example.com/a.md">')

    def test_site_index_stops_at_marker(self):
        text = 'head\n\n<!-- SITE-INDEX-END: x -->\n\ntail\n'
        self.assertEqual(site_index_text(text), 'head\n')
        self.assertEqual(site_index_text('no marker\n'), 'no marker\n')

    def test_tables_are_wrapped_for_scrolling(self):
        self.assertEqual(wrap_tables('<table><tr></tr></table>'), '<div class="table-scroll"><table><tr></tr></table></div>')

    def test_headings_ignore_code_fences(self):
        found, closed = headings('# a\n```\n# not a heading\n```\n## b\n')
        self.assertEqual(found, [(1, 'a'), (2, 'b')])
        self.assertTrue(closed)
        self.assertFalse(headings('# a\n```\ncode\n')[1])

    def test_url_followed_by_japanese_is_detected(self):
        self.assertIsNotNone(BARE_URL.search('https://example.com/a仕様'))
        self.assertIsNone(BARE_URL.search('https://example.com/a （仕様）'))
        self.assertIsNone(BARE_URL.search('see https://example.com/a'))

    def test_section_toc_lists_headings_of_one_level(self):
        body = '<h2 id="a">一</h2><p>x</p><h3 id="b">下位</h3><h2 id="c">二</h2>'
        toc = section_toc(body, 2, 'この回の節')
        self.assertIn('<a href="#a">一</a>', toc)
        self.assertIn('<a href="#c">二</a>', toc)
        self.assertNotIn('#b', toc)
        self.assertIn('（2節）', toc)
        self.assertEqual(section_toc('<p>x</p>', 2, 's'), '')

    def test_status_note_only_when_defined(self):
        self.assertEqual(status_note({'path': 'x'}), '')
        note = status_note({'status': {'label': '設計案', 'text': '未実装です。'}})
        self.assertIn('role="note"', note)
        self.assertIn('設計案', note)

    def test_chapters_three_and_four_carry_status_labels(self):
        chapters = {c['number']: c for c in load_series()['chapters']}
        self.assertIn('設計案', chapters[3]['status']['label'])
        self.assertIn('実験計画', chapters[4]['status']['label'])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build(out)
            for name in ('03-from-reading-to-mining-agent', '04-reimplementing-old-ideas'):
                page = (out / 'articles' / f'{name}.html').read_text(encoding='utf-8')
                self.assertIn('class="status"', page)
            for number in range(1, 5):
                page = next((out / 'articles').glob(f'0{number}-*.html')).read_text(encoding='utf-8')
                self.assertNotIn('この回の事実確認の内容と未解決事項は', page)
                self.assertIn('class="toc"', page)

    def test_log_rows_are_classified(self):
        self.assertEqual(row_kinds('確認済み：本文で確認', 'なし'), ['confirmed'])
        self.assertEqual(row_kinds('修正：書き換えた', '二次情報のみ'), ['fixed', 'open'])
        self.assertEqual(row_kinds('確認済みと修正：両方', 'なし'), ['confirmed', 'fixed'])
        self.assertEqual(row_kinds('事実主張ではないため変更なし', 'なし'), [])

    def test_log_tables_get_labels_and_kinds(self):
        table = ('<div class="table-scroll"><table><thead><tr><th>確認結果</th><th>残課題</th></tr></thead>'
                 '<tbody><tr class="odd"><td>修正：直した</td><td>なし</td></tr></tbody></table></div>')
        out = annotate_log_tables(table)
        self.assertIn('<div class="table-scroll" data-cases data-kinds="fixed">', out)
        self.assertIn('<tr class="odd" data-kinds="fixed">', out)
        self.assertIn('data-label="確認結果"', out)
        self.assertIn('data-label="残課題"', out)
        plain = annotate_log_tables('<div class="table-scroll"><table><thead><tr><th>略号</th></tr></thead><tbody><tr><td>E62</td></tr></tbody></table></div>')
        self.assertNotIn('data-cases', plain)
        self.assertNotIn('data-kinds', plain)

    def test_log_page_has_filter_and_every_case_row_is_annotated(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build(out)
            log = (out / 'editorial' / 'verification-log.html').read_text(encoding='utf-8')
            self.assertIn('class="log-filter"', log)
            self.assertEqual(log.count('data-cases'), 4)
            for input_id in ('f-all', 'f-confirmed', 'f-fixed', 'f-open'):
                self.assertIn(f'id="{input_id}"', log)

    def test_readers_are_not_pointed_to_the_verification_log(self):
        """検証ログは編集側の記録であり、読者向けページから辿る導線を置かない。"""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build(out)
            for page in out.rglob('*.html'):
                if page.name == 'verification-log.html':
                    continue
                text = page.read_text(encoding='utf-8')
                self.assertNotIn('verification-log', text, page.name)
                self.assertNotIn('検証ログ', text, page.name)

    def test_css_does_not_nest_has(self):
        """:has() の中の :has() は無効で、ルール全体がブラウザに捨てられる。"""
        css = (ROOT / 'site-src' / 'styles.css').read_text(encoding='utf-8')
        i = 0
        while (i := css.find(':has(', i)) != -1:
            depth, j = 1, i + len(':has(')
            while depth and j < len(css):
                depth += {'(': 1, ')': -1}.get(css[j], 0)
                j += 1
            self.assertNotIn(':has(', css[i + len(':has('):j], css[i:j][:80])
            i = j

    def test_complete_page_links_chapters_in_page(self):
        chapters = load_series()['chapters']
        html_in = '<a href="02-excavating-forgotten-designs.html#参考文献">x</a>'
        self.assertEqual(localize_chapter_links(html_in, chapters), '<a href="#ch2-参考文献">x</a>')


GOOD_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10" role="img">'
            '<title>t</title><desc>d</desc>{body}</svg>')


class FigureTests(unittest.TestCase):
    def svg_problems(self, body: str, **replace) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'x.svg'
            path.write_text(GOOD_SVG.format(body=body).replace('role="img"', replace.get('role', 'role="img"')), encoding='utf-8')
            return svg_errors(path)

    def test_figures_match_series_and_chapter_text(self):
        result, errors = validate()
        self.assertEqual(errors, [])
        expected = sum(len(c.get('figures', [])) for c in load_series()['chapters'])
        self.assertEqual((result.figures, result.svg_files), (expected, expected + 1))  # 表紙は回に属さない

    def test_committed_svgs_are_what_the_generator_produces(self):
        """SVGを直接編集すると、次の再生成で上書きされる。生成コードと成果物のずれを検出する。"""
        original = draw_figures.OUT
        with tempfile.TemporaryDirectory() as tmp:
            try:
                draw_figures.OUT = Path(tmp)
                names = [draw() for draw in draw_figures.FIGURES]
            finally:
                draw_figures.OUT = original
            series = load_series()
            self.assertEqual(names, [Path(series['cover']).name] + [n for c in series['chapters'] for n in c.get('figures', [])])
            for name in names:
                self.assertEqual((Path(tmp) / name).read_text(encoding='utf-8'), (original / name).read_text(encoding='utf-8'), name)

    def test_generator_rejects_text_that_does_not_fit(self):
        fig = draw_figures.Figure(9, 'a', 'x', 'タイトル', '副題')
        with self.assertRaises(ValueError):
            fig.text(1100, 300, 'これは画面の右端からはみ出す長い文である', 24)
        with self.assertRaises(ValueError):
            fig.para(50, 300, 100, ['この一行は百ピクセルの幅に収まらない'], 16)
        with self.assertRaises(ValueError):
            fig.box(50, 300, 80, 40, '幅の狭い箱に入らない題名')

    def test_generator_keeps_small_text_readable(self):
        fig = draw_figures.Figure(9, 'a', 'x', 'タイトル', '副題')
        fig.text(50, 300, '小さな文字', 8)
        self.assertIn('font-size="14"', fig.body[-1])

    def test_svg_checks_accept_a_passive_svg_and_reject_active_ones(self):
        self.assertEqual(self.svg_problems('<text font-size="14">a</text>'), [])
        self.assertTrue(any('script' in e for e in self.svg_problems('<script>alert(1)</script>')))
        self.assertTrue(any('foreignObject' in e for e in self.svg_problems('<foreignObject/>')))
        self.assertTrue(any('event handler' in e for e in self.svg_problems('<rect onclick="x()"/>')))
        self.assertTrue(any('external' in e for e in self.svg_problems('<use href="https://example.com/a.svg#b"/>')))
        self.assertTrue(any('below 14px' in e for e in self.svg_problems('<text font-size="12">a</text>')))
        self.assertTrue(any('role="img"' in e for e in self.svg_problems('', role='')))

    def test_figure_and_caption_become_one_figure_element(self):
        html_in = '<p><img src="../assets/illustrations/a.svg" alt="代替 &amp; 説明" /></p>\n<p><em>図1-1：説明。</em></p>'
        out = wrap_figures(html_in)
        self.assertIn('<figure>', out)
        self.assertIn('<figcaption>図1-1：説明。</figcaption>', out)
        self.assertIn('alt="代替 &amp; 説明"', out)
        self.assertIn('href="../assets/illustrations/a.svg"', out)
        plain = '<p><img src="a.svg" alt="x" /></p>\n<p><em>次回：第2回</em></p>'
        self.assertEqual(wrap_figures(plain), plain)
        self.assertEqual(relocate_assets('src="../assets/illustrations/a.svg"'), 'src="assets/illustrations/a.svg"')

    def test_built_site_embeds_every_figure_with_alt_and_caption(self):
        chapters = load_series()['chapters']
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build(out)
            for c in chapters:
                page = (out / 'articles' / f'{Path(c["path"]).stem}.html').read_text(encoding='utf-8')
                self.assertEqual(page.count('<figure>'), len(c['figures']))
                self.assertEqual(page.count('<figcaption>図'), len(c['figures']))
                for name in c['figures']:
                    self.assertIn(f'src="../assets/illustrations/{name}"', page)
                    self.assertTrue((out / 'assets' / 'illustrations' / name).exists())
            complete = (out / 'complete.html').read_text(encoding='utf-8')
            self.assertEqual(complete.count('<figure>'), sum(len(c['figures']) for c in chapters))
            self.assertNotIn('src="../assets/', complete)
            self.assertNotIn('<img src="http', complete)

    def test_index_page_shows_the_cover_without_caption(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build(out)
            index = (out / 'index.html').read_text(encoding='utf-8')
            self.assertIn('<figure class="cover">', index)
            self.assertIn('src="assets/illustrations/00-cover.svg"', index)
            self.assertNotIn('<figcaption>', index)
            self.assertTrue((out / 'assets' / 'illustrations' / '00-cover.svg').exists())

    def test_concept_images_are_labelled_and_never_figures_of_fact(self):
        """比喩のイメージ図は、図の中のバッジと、キャプションの「（イメージ）」で区別する。"""
        for c in load_series()['chapters']:
            text = (ROOT / c['path']).read_text(encoding='utf-8')
            captions = dict(re.findall(r'^\*図(\d+-\d+)：(.+)\*$', text, re.M))
            for index, name in enumerate(c['figures'], 1):
                svg = (ROOT / 'assets' / 'illustrations' / name).read_text(encoding='utf-8')
                badge = '>イメージ</text>' in svg
                self.assertEqual(captions[f'{c["number"]}-{index}'].startswith('（イメージ）'), badge, name)

    def test_figure_references_that_disagree_with_series_json_are_reported(self):
        chapter = dict(load_series()['chapters'][0])
        text = (ROOT / chapter['path']).read_text(encoding='utf-8')
        errors: list[str] = []
        chapter['figures'] = chapter['figures'][:1]
        check_figures(chapter, text, errors, Result())
        self.assertTrue(any('must match series.json' in e for e in errors), errors)
        self.assertTrue(any('caption' in e for e in errors), errors)
        errors = []
        chapter = load_series()['chapters'][0]
        blank_alt = re.sub(r'^!\[[^\]]*\]', '![]', text, count=1, flags=re.M)
        check_figures(chapter, blank_alt, errors, Result())
        self.assertTrue(any('missing alt text' in e for e in errors), errors)


if __name__ == '__main__':
    unittest.main()
