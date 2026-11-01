from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build import build, load_series, map_md_links, site_index_text, wrap_tables  # noqa: E402
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


if __name__ == '__main__':
    unittest.main()
