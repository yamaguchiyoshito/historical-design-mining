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
        self.figures = 0
        self.images_without_alt = 0
        self.label_targets: list[str] = []
        self.vignettes = 0
        self._in_vignette = False
        self.feed(text)

    def handle_endtag(self, tag):
        if tag == 'div':
            self._in_vignette = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script':
            self.scripts += 1
        if tag == 'h1':
            self.h1 += 1
        if tag == 'label' and 'for' in attrs:
            self.label_targets.append(attrs['for'])
        if tag == 'figure':
            self.figures += 1
        if tag == 'div' and 'vignette' in attrs.get('class', '').split():
            self._in_vignette = True
            self.vignettes += 1
        if tag == 'img' and not attrs.get('alt', '').strip() and not self._in_vignette:
            self.images_without_alt += 1
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
        for target in doc.label_targets:
            if target not in doc.ids:
                errors.append(f'{name}: label points to a missing control #{target}')
        if doc.images_without_alt:
            errors.append(f'{name}: {doc.images_without_alt} image(s) without alt text')
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
    total = 0
    vignette_total = 0
    for c in series['chapters']:
        want = len(c.get('figures', []))
        total += want
        vignettes_wanted = len(c.get('vignettes', []))
        vignette_total += vignettes_wanted
        page = site / 'articles' / (Path(c['path']).stem + '.html')
        if page.resolve() in docs and docs[page.resolve()].vignettes != vignettes_wanted:
            errors.append(f'{page.name}: expected {vignettes_wanted} vignettes, found {docs[page.resolve()].vignettes}')
        if page.resolve() in docs and docs[page.resolve()].figures != want:
            errors.append(f'{page.name}: expected {want} figures, found {docs[page.resolve()].figures}')
    index = (site / 'index.html').resolve()
    if index in docs and docs[index].figures != (1 if series.get('cover') else 0):
        errors.append(f'index.html: expected the cover figure, found {docs[index].figures} figures')
    complete = (site / 'complete.html').resolve()
    if complete in docs and docs[complete].figures != total:
        errors.append(f'complete.html: expected {total} figures, found {docs[complete].figures}')
    covers = [Path(series['cover']).name] if series.get('cover') else []
    if complete in docs and docs[complete].vignettes != vignette_total:
        errors.append(f'complete.html: expected {vignette_total} vignettes, found {docs[complete].vignettes}')
    for name in covers + [n for c in series['chapters'] for n in c.get('figures', [])]:
        if not (site / 'assets' / 'illustrations' / name).exists():
            errors.append(f'Missing assets/illustrations/{name}')
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
