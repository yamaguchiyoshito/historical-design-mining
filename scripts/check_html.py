#!/usr/bin/env python3
"""Verify generated HTML: links, unique IDs, offline assets, no scripts."""
from __future__ import annotations
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[tuple[str, str, str]] = []
        self.scripts = 0
        self.h1 = 0
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script':
            self.scripts += 1
        if tag == 'h1':
            self.h1 += 1
        for attr in ('href', 'src'):
            if attr in attrs:
                self.links.append((tag, attr, attrs[attr]))


def check(site: Path) -> dict:
    site = site.resolve()
    errors: list[str] = []
    docs = {p.resolve(): Document(p.read_text(encoding='utf-8')) for p in sorted(site.rglob('*.html'))}
    for path, doc in docs.items():
        name = path.relative_to(site)
        for ident, n in Counter(doc.ids).items():
            if n > 1:
                errors.append(f'{name}: duplicate ID {ident}')
        if doc.scripts:
            errors.append(f'{name}: unexpected script')
        if name.name != 'complete.html' and doc.h1 != 1:
            errors.append(f'{name}: expected one h1, found {doc.h1}')
        for tag, attr, url in doc.links:
            parsed = urlsplit(url)
            if parsed.scheme:
                if attr == 'src':
                    errors.append(f'{name}: external resource dependency {url}')
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not target.is_relative_to(site):
                errors.append(f'{name}: link escapes output: {url}')
            elif not target.exists():
                errors.append(f'{name}: missing target {url}')
            elif parsed.fragment and target in docs and unquote(parsed.fragment) not in docs[target].ids:
                errors.append(f'{name}: missing anchor {url}')
    series = json.loads((ROOT / 'series.json').read_text(encoding='utf-8'))
    expected = len(series['chapters']) + 3  # index, complete, verification log
    if len(docs) != expected:
        errors.append(f'Expected {expected} HTML pages, found {len(docs)}')
    for rel in ('assets/styles.css', '.nojekyll'):
        if not (site / rel).exists():
            errors.append(f'Missing {rel}')
    return {'html_pages': len(docs), 'errors': errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / '_site')
    args = parser.parse_args()
    report = check(args.site)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
