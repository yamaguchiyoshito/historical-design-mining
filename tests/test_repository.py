from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build import (annotate_log_tables, build, load_series, localize_chapter_links, map_md_links, row_kinds,  # noqa: E402
                   section_toc, site_index_text, status_note, wrap_tables)
from check_html import check  # noqa: E402
from validate import validate, headings, BARE_URL  # noqa: E402


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
                self.assertIn(f'verification-log.html#第{number}回', page)
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


if __name__ == '__main__':
    unittest.main()
