#!/usr/bin/env python3
"""Generate every SVG illustration used in articles/ deterministically. Stdlib only.

図の方針: 1枚につき主張は1つ、パネルは2枚まで、ラベルは10個前後。矢印や色だけに意味を依存させず、ラベルでも区別する。
SVGには viewBox / role="img" / title / desc を持たせ、script・外部参照・フォントファイルは入れない。
未実施の実験・未実装の設計は、図の中にも「設計案」「例示」「実験計画（未実施）」のバッジを描く。
文字の幅は等幅の近似で見積もり、枠や画面からはみ出す文は生成時にエラーにする。
"""
from __future__ import annotations
from html import escape
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets' / 'illustrations'
BG, INK, MUTED, LINE, SOFT = '#f7f5ef', '#232a33', '#5d6873', '#d8d4c8', '#ece9e0'
BLUE, AMBER, TEAL, PLUM = '#2b5f9e', '#c7792b', '#2f8f83', '#8a4f9e'
FONT = 'system-ui, -apple-system, "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP", Meiryo, sans-serif'
CODE = 'HISTORICAL DESIGN MINING'
WIDTH = 1200
EDGE = 24  # 文字が画面端に寄りすぎないための余白


def tw(s: str, size: float) -> float:
    """Estimated rendered width of s at the given font size (CJK = 1em, Latin = 0.6em)."""
    total = 0.0
    for c in s:
        if ord(c) >= 0x2000:
            total += size
        elif c.isupper() or c in 'mwMW':
            total += size * 0.7
        elif c in ' ,.:;!|il1()[]\'':
            total += size * 0.35
        else:
            total += size * 0.6
    return total


class Figure:
    MIN_TEXT = 14

    def __init__(self, chapter: int, part: str, slug: str, title: str, subtitle: str, height: int = 640, badge: str = ''):
        self.chapter, self.part, self.slug = chapter, part, slug
        self.index = ord(part) - 96
        self.h = height
        self.title, self.subtitle = title, subtitle
        self.defs: list[str] = []
        self._markers: dict[str, str] = {}
        self.body: list[str] = []
        self.name = f'{chapter:02d}-{part}-{slug}.svg'
        self.label = f'図{chapter}-{self.index}'
        self.text(50, 52, f'{CODE}     {chapter:02d}     {self.label}', 18, BLUE, weight=700)
        self.text(50, 103, title, 34, weight=700)
        self.text(50, 141, subtitle, 21, MUTED)
        self.line(50, 166, 1150, 166, color=LINE, width=1)
        if badge:
            self.badge(1150, 34, badge, AMBER, anchor='end')

    # --- primitives -------------------------------------------------------
    def _check_x(self, x: float, s: str, size: float, anchor: str) -> None:
        w = tw(s, size)
        left = x - (w / 2 if anchor == 'middle' else w if anchor == 'end' else 0)
        if left < EDGE - 0.5 or left + w > WIDTH - EDGE + 0.5:
            raise ValueError(f'{self.name}: text runs off the canvas ({left:.0f}..{left + w:.0f}): {s}')

    def text(self, x, y, s, size=24, color=INK, anchor='start', weight=400):
        size = max(size, self.MIN_TEXT)
        self._check_x(x, str(s), size, anchor)
        self.body.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{escape(str(s))}</text>')

    def para(self, x, y, w, lines, size=16, color=INK, anchor='start', gap=None, weight=400):
        """Lines of text that must each fit in w pixels. An empty string leaves a blank line."""
        size = max(size, self.MIN_TEXT)
        gap = gap or round(size * 1.45)
        for i, s in enumerate(lines):
            if s and tw(s, size) > w + 0.5:
                raise ValueError(f'{self.name}: line is {tw(s, size):.0f}px wide but only {w:.0f}px is available: {s}')
            if s:
                self.text(x, y + i * gap, s, size, color, anchor, weight)

    def _marker(self, color):
        if color not in self._markers:
            mid = f'arrow-{color.lstrip("#")}'
            self._markers[color] = mid
            self.defs.append(f'<marker id="{mid}" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="{color}" stroke-width="1.4"/></marker>')
        return self._markers[color]

    def _stroke_extra(self, color, arrow, both, dash):
        extra = ''
        if arrow or both:
            extra += f' marker-end="url(#{self._marker(color)})"'
        if both:
            extra += f' marker-start="url(#{self._marker(color)})"'
        if dash:
            extra += ' stroke-dasharray="8 7"'
        return extra

    def line(self, x1, y1, x2, y2, color=MUTED, width=2, arrow=False, both=False, dash=False):
        self.body.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{self._stroke_extra(color, arrow, both, dash)}/>')

    def elbow(self, points, color=MUTED, width=2, arrow=True, dash=False):
        d = 'M ' + ' L '.join(f'{x:.1f} {y:.1f}' for x, y in points)
        self.body.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"{self._stroke_extra(color, arrow, False, dash)}/>')

    def rect(self, x, y, w, h, fill='#ffffff', stroke=LINE, width=2, rx=12, dash=False):
        extra = ' stroke-dasharray="8 7"' if dash else ''
        self.body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{extra}/>')

    def box(self, x, y, w, h, title, subtitle='', color=BLUE, size=22, dash=False, fill='#ffffff'):
        if tw(title, size) > w - 24:
            raise ValueError(f'{self.name}: box title does not fit: {title}')
        self.rect(x, y, w, h, fill=fill, stroke=color, rx=14, dash=dash)
        self.text(x + w / 2, y + (h / 2 + 8 if not subtitle else h / 2 - 4), title, size, color, anchor='middle', weight=700)
        if subtitle:
            if tw(subtitle, 17) > w - 24:
                raise ValueError(f'{self.name}: box subtitle does not fit: {subtitle}')
            self.text(x + w / 2, y + h / 2 + 22, subtitle, 17, MUTED, anchor='middle')

    def circ(self, x, y, r=10, color=BLUE):
        self.body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"/>')

    def numbered(self, x, y, n, color=BLUE, r=17):
        self.circ(x, y, r, color)
        self.text(x, y + 6, n, 18, '#ffffff', anchor='middle', weight=700)

    def panel(self, x, y, w, h, color='#c9c4b6', dash=True):
        self.rect(x, y, w, h, fill='none', stroke=color, rx=16, dash=dash)

    def chip(self, x, y, label, color, size=16, dash=False, fill='#ffffff', height=32, anchor='start'):
        """A pill label; returns its width."""
        w = tw(label, size) + 26
        left = x - w if anchor == 'end' else x
        self.rect(left, y, w, height, fill=fill, stroke=color, width=2, rx=height // 2, dash=dash)
        self.text(left + w / 2, y + height / 2 + size * 0.35, label, size, color, anchor='middle', weight=700)
        return w

    def badge(self, x, y, label, color, anchor='start'):
        return self.chip(x, y, label, color, size=15, fill='#ffffff', height=28, anchor=anchor)

    def legend(self, x, y, items, gap=30):
        """items: (kind, color, label); kind is 'box', 'dashbox', 'line', 'thick' or 'dash'. Drawn top to bottom."""
        for i, (kind, color, label) in enumerate(items):
            yy = y + i * gap
            if kind in ('box', 'dashbox'):
                self.rect(x, yy - 12, 26, 16, fill='#ffffff', stroke=color, width=2, rx=4, dash=kind == 'dashbox')
            else:
                self.line(x, yy - 4, x + 26, yy - 4, color=color, width={'line': 2, 'thick': 5}.get(kind, 3), dash=kind == 'dash')
            self.text(x + 38, yy + 2, label, 15, MUTED)

    def footer(self, s):
        self.text(50, self.h - 28, s, 19, MUTED)

    def save(self) -> str:
        OUT.mkdir(parents=True, exist_ok=True)
        head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{self.h}" viewBox="0 0 {WIDTH} {self.h}" role="img" aria-labelledby="title desc">',
                f'<title id="title">{escape(self.title)}</title>', f'<desc id="desc">{escape(self.subtitle)}</desc>',
                '<defs>' + ''.join(self.defs) + '</defs>', f'<rect width="{WIDTH}" height="{self.h}" rx="20" fill="{BG}"/>',
                f'<g font-family=\'{FONT}\'>']
        (OUT / self.name).write_text('\n'.join(head + self.body + ['</g>', '</svg>']) + '\n', encoding='utf-8')
        return self.name


# ---------------------------------------------------------------------------
# 第1回
# ---------------------------------------------------------------------------
def fig_1a() -> str:
    f = Figure(1, 'a', 'why-not-inherited', '実現されなかった理由は、一つではない',
               '現代の技術で再検討できるものと、再実装しても残るものを分ける', 680)
    f.box(400, 196, 400, 60, '実装されなかった構想', color=INK)
    cols = [
        (50, TEAL, '現代の技術で再検討できる', '条件が変われば、試す余地がある',
         [('計算資源の不足', ''), ('データの不足', '')]),
        (430, AMBER, '変わったかを個別に確認する', '現在の条件で解消したかを調べる',
         [('経済性', '製造や運用に見合わなかった'), ('標準・制度・組織の慣行', '合わなかった'), ('社会の需要', 'まだ必要とされていなかった')]),
        (810, PLUM, '再実装でも同じ壁に当たる', '条件が変わっても残る',
         [('原理的な限界', '実装を試みて初めてわかった')]),
    ]
    for x, color, title, sub, items in cols:
        cx = x + 170
        f.elbow([(600, 256), (600, 286), (cx, 286), (cx, 316)], color=color)
        f.rect(x, 318, 340, 292, stroke=color, rx=16)
        f.text(cx, 358, title, 22, color, anchor='middle', weight=700)
        f.text(cx, 386, sub, 16, MUTED, anchor='middle')
        f.line(x + 20, 404, x + 320, 404, color=LINE, width=1)
        for i, (name, note) in enumerate(items):
            y = 444 + i * 60
            f.circ(x + 28, y - 6, 5, color)
            f.text(x + 46, y, name, 19, INK, weight=700)
            if note:
                f.text(x + 46, y + 24, note, 15, MUTED)
    f.footer('どの理由だったかで、再実装を試す意味が変わる。')
    return f.save()


def fig_1b() -> str:
    f = Figure(1, 'b', 'series-map', '連載の見取り図', 'なぜ、何を、どう発掘し、どう検証するか', 640)
    cards = [
        ('第1回', 'なぜ', ['過去の文章を設計書', 'として読む仮説と、', 'その限界を示す。'], ''),
        ('第2回', '何を', ['エンゲルバートと', 'アレグザンダーの原典', 'から、実現された部分', 'と残された部分を', '区別する。'], ''),
        ('第3回', 'どう発掘する', ['探索、継承調査、', '仕様化、評価の', '四工程を入力・出力・', '失敗条件つきで', '設計する。'], '設計案'),
        ('第4回', 'どう検証する', ['忠実な再現と現代的', '拡張を区別し、比較', '実験の条件を示す。'], '実験計画（未実施）'),
    ]
    for i, (kicker, key, lines, badge) in enumerate(cards):
        x = 50 + i * 285
        f.rect(x, 210, 245, 290, stroke=BLUE, rx=16)
        f.text(x + 22, 246, kicker, 16, MUTED, weight=700)
        f.text(x + 22, 292, key, 28, BLUE, weight=700)
        f.line(x + 22, 312, x + 223, 312, color=LINE, width=1)
        f.para(x + 22, 346, 205, lines, 16, gap=23)
        if badge:
            f.badge(x + 22, 456, badge, AMBER)
        if i < 3:
            f.line(x + 245, 355, x + 285, 355, color=BLUE, width=2.5, arrow=True)
    f.elbow([(1027, 500), (1027, 548), (172, 548), (172, 502)], color=MUTED, dash=True)
    f.text(600, 536, '第4回で、第1回の問いに戻る', 16, MUTED, anchor='middle')
    f.footer('各回は単独でも読めるが、問いは次の回へ手渡される。')
    return f.save()


# ---------------------------------------------------------------------------
# 第2回
# ---------------------------------------------------------------------------
def fig_2a() -> str:
    f = Figure(2, 'a', 'h-lam-t', 'H-LAM/T：人間を中心にした一つの系', '言語・人工物・方法論・訓練を含めて、系として設計する', 700)
    f.panel(50, 200, 720, 400)
    f.box(320, 360, 180, 80, '人間', 'Human', color=BLUE)
    f.box(300, 225, 220, 70, '方法論', 'Methodology', color=BLUE, size=20)
    f.box(300, 505, 220, 70, '訓練', 'Trained', color=BLUE, size=20)
    f.box(70, 360, 190, 80, '言語', 'Language', color=BLUE, size=20)
    f.box(560, 360, 190, 80, '人工物', 'Artifacts', color=BLUE, size=20)
    f.line(410, 295, 410, 360, color=BLUE, both=True)
    f.line(410, 440, 410, 505, color=BLUE, both=True)
    f.line(260, 400, 320, 400, color=BLUE, both=True)
    f.line(500, 400, 560, 400, color=BLUE, both=True)
    f.text(50, 628, 'H-LAM/T = Human using Language, Artifacts, Methodology, in which he is Trained', 15, MUTED)
    f.rect(800, 200, 350, 200, stroke=BLUE, rx=14)
    f.text(822, 234, '原典が述べたこと', 20, BLUE, weight=700)
    f.text(822, 258, '1962年報告書の定義', 15, MUTED)
    f.para(822, 292, 310, ['人間が、言語・人工物・', '方法論を用い、そのため', 'の訓練を受ける。これら', 'を一つのシステムとして', '捉えて設計する。'], 17, gap=21)
    f.rect(800, 420, 350, 190, stroke=AMBER, rx=14, dash=True)
    f.text(822, 454, '筆者の現代的な解釈', 20, AMBER, weight=700)
    f.text(822, 478, '検証すべき仮説', 15, MUTED)
    f.para(822, 512, 310, ['生成AIも、AI単体では', 'なく、人間・言語・道具・', '作業手順・学習の仕組み', 'を含む系全体で評価する。'], 17, gap=21)
    f.footer('改善の対象は個々の道具ではなく、系全体である。')
    return f.save()


def fig_2b() -> str:
    f = Figure(2, 'b', 'alexander-lineage', 'アレグザンダーの初期の方法と後期の系譜',
               '初期の形式的な分割方法と、パターン・ランゲージを同一視しない', 770)
    f.legend(50, 202, [('box', BLUE, 'アレグザンダー本人の著作・記述')])
    f.legend(480, 202, [('box', TEAL, '後続の研究')])
    f.panel(50, 224, 1100, 276, color='#c9c4b6', dash=False)
    f.text(74, 258, '初期の形式的な分割方法', 20, INK, weight=700)
    f.line(90, 326, 1130, 326, color=MUTED, width=2, arrow=True)
    events = [
        (160, BLUE, '1962', ['博士論文が', '完成した', '（1964年の著作の', 'もとになった）']),
        (380, BLUE, '1964', ['『Notes on the', 'Synthesis of Form』', 'を出版した']),
        (600, BLUE, '1965', ['「A City Is Not', 'a Tree」を発表。', '木構造への分割を', '退けた*']),
        (820, BLUE, '1971', ['ペーパーバック版', '序文で、形式的で', '複雑な数学的方法は', '不要だったと述べた*']),
        (1040, TEAL, '2023', ['Gabrielの論考。', '村落の分解を計算', '機で再現しようと', 'して、一致せず']),
    ]
    for x, color, year, lines in events:
        f.text(x, 306, year, 22, color, anchor='middle', weight=700)
        f.circ(x, 326, 8, color)
        f.rect(x - 100, 348, 200, 130, stroke=color, rx=12)
        f.para(x - 86, 376, 176, lines, 16, gap=22)
    f.line(922, 340, 938, 312, color=MUTED, width=2)
    f.line(932, 340, 948, 312, color=MUTED, width=2)
    f.text(50, 526, '* 1965年と1971年の内容は、Gabriel（2023）の記述による。年表の間隔は等間隔ではない。', 14, MUTED)
    f.text(600, 580, '≠　同一視しない', 22, AMBER, anchor='middle', weight=700)
    f.panel(50, 604, 1100, 84, color=MUTED, dash=True)
    f.text(74, 636, '後期のパターン・ランゲージ', 20, INK, weight=700)
    f.text(74, 666, 'ソフトウェア分野で広く受け入れられた系譜。初期の形式的な分割方法とは別に扱う。', 17, MUTED)
    f.footer('同じ人の研究でも、時期と方法が違えば別のものとして扱う。')
    return f.save()


def fig_2c() -> str:
    f = Figure(2, 'c', 'origin-vs-successors', '原典・後続・筆者の解釈を分けて読む',
               'エンゲルバートとアレグザンダーを、三つの区分で並べる', 740)
    heads = [(215, BLUE, '原典が明示したこと', '著者自身の記述', False),
             (530, TEAL, '実現・継承されたこと', '実装と後続の研究', False),
             (845, AMBER, '筆者の解釈・仮説', '検証すべき仮説', True)]
    for x, color, title, sub, dash in heads:
        f.rect(x, 196, 300, 62, stroke=color, rx=12, dash=dash)
        f.text(x + 150, 224, title, 19, color, anchor='middle', weight=700)
        f.text(x + 150, 246, sub, 14, MUTED, anchor='middle')
    rows = [
        (270, 'エンゲルバート', '1962・1968', [
            ['H-LAM/T：人間・言語・', '人工物・方法論・訓練', 'を一つの系として捉える。', '研究集団が、自分たちの', '道具をまず自分たちで', '開発することを勧めた。'],
            ['NLSは、研究グループの', '実験環境で動作した。', '対話的な操作や共同作業は', '後に普及したが、NLSの', '直接の影響だけでは', '説明できない。'],
            ['人間とAIの知的作業', 'システム自体を継続的', 'に改善するAI。', '既に研究や実装があり、', '未実現とは断定できない。', '原典の構想で再調査する。']]),
        (470, 'アレグザンダー', '1964・2023', [
            ['要求を満たせていない', '状態をmisfitとして', '捉え、変数と相互作用', 'の分析で、複雑な設計', '問題を分解しようと', 'した。'],
            ['パターンの考え方は', 'ソフトウェアで広く', '受け入れられたが、それ', 'は後期の系譜である。', 'Gabriel（2023）は初期', 'の方法を再現できず。'],
            ['要求間の関係を生成AI', 'で抽出し、グラフ分割', 'から設計候補を得て、', '結合度などで評価する。', '検証はこれからである。']]),
    ]
    for y, name, years, cells in rows:
        f.rect(50, y, 150, 180, fill=SOFT, stroke=LINE, rx=12)
        f.text(125, y + 86, name, 18, INK, anchor='middle', weight=700)
        f.text(125, y + 112, years, 14, MUTED, anchor='middle')
        for (x, color, _, _, dash), lines in zip(heads, cells):
            f.rect(x, y, 300, 180, stroke=color, rx=12, dash=dash)
            f.para(x + 16, y + 34, 272, lines, 16, gap=23)
    f.footer('一つの語りに、原典・後続・筆者の解釈が混ざらないようにする。')
    return f.save()


# ---------------------------------------------------------------------------
# 第3回
# ---------------------------------------------------------------------------
def fig_3a() -> str:
    f = Figure(3, 'a', 'lineage-four-states', '継承状態は四つに分けて記録する',
               '「見つからなかった」ことと「存在しない」ことは別である', 700, badge='設計案')
    f.text(50, 214, '対応する実装が見つかった', 18, MUTED, weight=700)
    states = [('既に実現されている', ''), ('一部の機能や原理だけが', '実現されている'), ('実装の試みはあるが、', '十分な成果が得られていない')]
    for i, (a, b) in enumerate(states):
        x = 50 + i * 377
        f.rect(x, 232, 346, 110, stroke=TEAL, rx=14)
        f.numbered(x + 36, 287, str(i + 1), TEAL)
        if b:
            f.text(x + 70, 280, a, 19, INK, weight=700)
            f.text(x + 70, 306, b, 19, INK, weight=700)
        else:
            f.text(x + 70, 294, a, 19, INK, weight=700)
    f.text(50, 388, '見つからなかった', 18, MUTED, weight=700)
    f.rect(50, 404, 1100, 124, stroke=AMBER, rx=14, dash=True)
    f.numbered(92, 466, '4', AMBER, r=19)
    f.text(130, 460, '調査した範囲では対応する実装が確認できない', 22, AMBER, weight=700)
    f.text(130, 496, '「未実装」と書いてはいけない。見つからなかったことと、存在しないことは異なる。', 18, INK)
    f.text(50, 578, '四つの状態のいずれでも記録する、調査範囲と不確実性', 19, INK, weight=700)
    x = 50
    for label in ['データベース', 'キーワード', '調べた年代', '見つかった類似技術', '判断できていない部分']:
        x += f.chip(x, 596, label, BLUE, size=17, height=36) + 14
    f.footer('調べた範囲を残すことで、「未実装」の断定を避けられる。')
    return f.save()


def fig_3b() -> str:
    f = Figure(3, 'b', 'spec-with-status', '仕様の各項目に、出所と区分を付ける',
               '原典にない項目は、補わずに「未定義」として残す', 730, badge='設計案')
    f.text(50, 214, '仕様の6項目', 20, INK, weight=700)
    items = [('目的', '何を解決するか'), ('入力', 'どのような情報を受け取るか'), ('出力', 'どのような結果を生成するか'),
             ('処理原理', 'どの関係や規則に基づいて動くか'), ('制約条件', '何を満たし、何を避けるべきか'), ('評価条件', 'なにをもって正しく動いたと判断するか')]
    for i, (name, note) in enumerate(items):
        y = 228 + i * 74
        f.rect(50, y, 380, 64, stroke=BLUE, rx=12)
        f.text(70, y + 28, name, 20, BLUE, weight=700)
        f.text(70, y + 51, note, 15, MUTED)
    f.line(430, 448, 500, 448, color=BLUE, width=2.5, arrow=True)
    f.panel(500, 228, 650, 438)
    f.text(524, 262, '各項目に付ける記録', 20, INK, weight=700)
    f.rect(524, 282, 602, 90, stroke=BLUE, rx=12)
    f.text(544, 314, '原文の位置', 19, BLUE, weight=700)
    f.text(544, 346, '節・段落・ページなど、原典のどこに基づくか', 16, INK)
    f.rect(524, 388, 602, 142, stroke=BLUE, rx=12)
    f.text(544, 420, '区分', 19, BLUE, weight=700)
    for i, (label, color, dash, note) in enumerate([('確認済み', BLUE, False, '原典に明記されている'),
                                                    ('推定', AMBER, False, '文脈や他の文献から導いた'),
                                                    ('未定義', MUTED, True, '原典に定義がない')]):
        y = 432 + i * 32
        f.chip(544, y, label, color, size=15, dash=dash, height=26)
        f.text(654, y + 19, note, 16, INK)
    f.rect(524, 546, 602, 100, stroke=AMBER, rx=12)
    f.text(544, 578, '補完の扱い', 19, AMBER, weight=700)
    f.para(544, 608, 562, ['原典にない項目は、未定義として残すか、現代の実装者の', '仮説として補完する。両者は区別して書く。'], 16, gap=22)
    f.footer('何が定義され、何が未定義なのかを明らかにする。')
    return f.save()


def fig_3c() -> str:
    f = Figure(3, 'c', 'four-steps-pipeline', '四つの工程と、その成果物',
               '各工程の出力が次の工程の入力になる。最初は一つのSkillで分けてもよい', 790, badge='設計案')
    f.text(50, 208, '工程（Skill）', 14, MUTED, weight=700)
    f.text(550, 208, '失敗とみなす条件', 14, MUTED, weight=700)
    f.text(880, 208, '成果物', 14, MUTED, weight=700)
    steps = [
        ('discover-historical-concepts', '現代の課題から、過去の問題設定と解決原理を発見する',
         ['原文の位置を示せない候補', 'がある。単語の類似だけで', '選んでいる。'], 'concept.md', '候補の問題設定と解決原理'),
        ('trace-technical-lineage', '継承関係を調べ、実現済みと残された可能性を整理する',
         ['見つからなかっただけで、', '「未実装」と断定する。'], 'lineage.md', '継承状態と調査範囲'),
        ('extract-design-specification', '入出力・処理原理・制約・評価条件を抽出して仕様化する',
         ['原典にない項目が、区分', 'なしに補完されている。'], 'specification.md', '原文位置・区分つきの仕様'),
        ('evaluate-reimplementation-value', '実装可能性・既存技術との差分・期待効果・検証コストを評価',
         ['比較対象がない。評価基準', 'が実験の後に決められる。'], 'evaluation.md', '評価と人間が判断する論点'),
    ]
    for i, (name, role, fail, out, note) in enumerate(steps):
        y = 220 + i * 112
        f.rect(50, y, 470, 82, stroke=BLUE, rx=12)
        f.numbered(80, y + 41, str(i + 1), BLUE)
        f.text(110, y + 36, name, 20, BLUE, weight=700)
        f.para(110, y + 62, 396, [role], 14)
        f.line(520, y + 41, 550, y + 41, color=BLUE, width=2.5, arrow=True)
        f.rect(550, y, 300, 82, stroke=AMBER, rx=12, dash=True)
        f.para(566, y + 32, 270, fail, 15, gap=20)
        f.line(850, y + 41, 880, y + 41, color=BLUE, width=2.5, arrow=True)
        f.rect(880, y, 270, 82, stroke=TEAL, rx=12)
        f.text(900, y + 36, out, 20, TEAL, weight=700)
        f.text(900, y + 62, note, 15, MUTED)
        if i < 3:
            f.line(285, y + 82, 285, y + 112, color=BLUE, width=2.5, arrow=True)
    f.rect(50, 676, 1100, 56, fill='none', stroke=MUTED, rx=12, dash=True)
    f.text(74, 710, 'sources.md ── 原典の書誌と原文位置の一覧。原典と調査結果の出所を保持する。', 17, INK)
    f.footer('価値の判断は研究者が担い、エージェントは判断の材料を整える。')
    return f.save()


# ---------------------------------------------------------------------------
# 第4回
# ---------------------------------------------------------------------------
def fig_4a() -> str:
    f = Figure(4, 'a', 'requirements-graph', '要求の関係から、分割の候補を考える',
               '要求をノード、関係をエッジとして構造を見る（関係は例示）', 690, badge='例示')
    f.panel(40, 208, 320, 290, color=TEAL)
    f.text(60, 238, 'まとまりの候補　注文変更と履歴', 15, TEAL, weight=700)
    f.panel(450, 208, 320, 290, color=TEAL)
    f.text(470, 238, 'まとまりの候補　注文確定と在庫', 15, TEAL, weight=700)
    nodes = {'R1': (60, 262, '注文を登録できる'), 'R4': (60, 410, '変更履歴を保存する'),
             'R2': (480, 262, '在庫数を超える注文を受け付けない'), 'R3': (480, 410, '注文確定時に在庫を引き当てる')}
    for key, (x, y, label) in nodes.items():
        f.rect(x, y, 260, 64, stroke=BLUE, rx=12)
        size = 15 if tw(label, 17) > 236 else 17
        f.text(x + 130, y + 38, label, size, INK, anchor='middle', weight=700)
        f.text(x + 14, y + 18, key, 14, MUTED, weight=700)
    f.line(190, 326, 190, 410, color=BLUE, width=2)
    f.text(206, 374, '注文変更と監査証跡', 16, BLUE)
    f.line(610, 326, 610, 410, color=BLUE, width=4)
    f.text(626, 374, '強い整合性制約', 16, BLUE)
    f.rect(830, 340, 280, 64, stroke=BLUE, rx=12)
    f.text(970, 378, '会計システムへ連携する', 17, INK, anchor='middle', weight=700)
    f.text(844, 358, 'R5', 14, MUTED, weight=700)
    f.text(830, 436, 'この例では関係を置いていない', 14, MUTED)
    f.rect(40, 546, 1110, 62, fill='#ffffff', stroke=AMBER, rx=14, dash=True)
    f.text(64, 584, '権限に応じて操作を制限する　── 複数の機能を横断する', 18, AMBER, weight=700)
    f.text(1126, 560, 'R6', 14, MUTED, anchor='end', weight=700)
    for x, ytop in [(190, 474), (610, 474)]:
        f.line(x, 546, x, ytop, color=AMBER, width=3, dash=True)
        f.circ(x, ytop, 5, AMBER)
    f.legend(810, 224, [('thick', BLUE, '強い整合性制約'), ('line', BLUE, '関係がある'), ('dash', AMBER, '複数の機能を横断する'), ('dashbox', TEAL, '関係から見えるまとまり')], gap=30)
    f.footer('グラフ上のまとまりは、そのままモジュールにはならない。')
    return f.save()


def fig_4b() -> str:
    f = Figure(4, 'b', 'who-does-what', '処理ごとに、担当する技術を使い分ける',
               '自然言語の解釈には生成AI、構造の計算には既存のアルゴリズム', 760, badge='設計案')
    xs = [186 + i * 190 for i in range(5)]
    w = 160
    heads = ['要求の識別', '関係の抽出', '構造の分析', '責務への変換', '実装と検証']
    for i, (x, name) in enumerate(zip(xs, heads)):
        f.text(x + w / 2, 214, f'{i + 1}　{name}', 16, INK, anchor='middle', weight=700)
    lanes = [(232, PLUM, ['生成AI']), (376, BLUE, ['既存の', 'アルゴリズム', '・開発ツール']), (520, AMBER, ['人間'])]
    for y, color, label in lanes:
        f.rect(40, y, 1110, 134, fill=SOFT, stroke=LINE, rx=14)
        f.para(54, y + 70 - (len(label) - 1) * 10, 118, label, 16, color, gap=22, weight=700)

    def cell(col, lane_y, color, title, body, dash=False):
        x, y = xs[col], lane_y + 12
        f.rect(x, y, w, 110, stroke=color, rx=12, dash=dash)
        f.text(x + 12, y + 26, title, 16, color, weight=700)
        f.para(x + 12, y + 48, w - 20, body, 14, gap=18)
        return x, y

    cell(0, 232, PLUM, '要求の識別', ['要求ごとにIDと', '原文の参照箇所を', '付ける'])
    cell(1, 232, PLUM, '関係の抽出', ['変更の影響・制約・', '依存を、根拠つき', 'で抽出する'])
    cell(1, 520, AMBER, '根拠の確認', ['不十分な関係を', '人間が確認する'], dash=True)
    cell(2, 376, BLUE, '構造の分析', ['グラフ分割で複数', '候補を計算し、結', 'びつきと依存を', '評価する'])
    cell(3, 232, PLUM, '責務への変換', ['候補を説明し、', '責務へ変換する。', '業務上の責務なども', '考慮する'])
    cell(4, 232, PLUM, 'コード生成', ['仕様からコード', 'を生成する'])
    cell(4, 376, BLUE, '開発ツール', ['テストを実行し、', '結果を確認する'])
    c = PLUM
    f.line(xs[0] + w, 299, xs[1], 299, color=c, width=2.5, arrow=True)
    f.line(xs[1] + w / 2, 354, xs[1] + w / 2, 532, color=AMBER, width=2.5, arrow=True, dash=True)
    f.elbow([(xs[1] + w, 286), (xs[1] + w + 15, 286), (xs[1] + w + 15, 420), (xs[2], 420)], color=c)
    f.elbow([(xs[1] + w, 576), (xs[1] + w + 15, 576), (xs[1] + w + 15, 462), (xs[2], 462)], color=AMBER)
    f.elbow([(xs[2] + w, 440), (xs[2] + w + 15, 440), (xs[2] + w + 15, 299), (xs[3], 299)], color=BLUE)
    f.line(xs[3] + w, 299, xs[4], 299, color=c, width=2.5, arrow=True)
    f.line(xs[4] + w / 2, 354, xs[4] + w / 2, 388, color=BLUE, width=2.5, arrow=True)
    f.legend(186, 690, [('line', MUTED, '実線：処理の流れ')])
    f.legend(450, 690, [('dash', AMBER, '破線：人間による確認')])
    f.footer('生成AIがすべてを担うのではなく、異なる技術をつなぐ。')
    return f.save()


def fig_4c() -> str:
    f = Figure(4, 'c', 'experiment-design', '比較実験の計画：三つの方法を同条件で比べる',
               '結果を見る前に、入力・指標・試行条件・レビューを固定する', 780, badge='実験計画（未実施）')
    f.rect(50, 204, 240, 298, stroke=BLUE, rx=14)
    f.text(70, 238, '同一の入力', 20, BLUE, weight=700)
    f.para(70, 272, 212, ['同じ要求仕様書と', '同じ制約を、三つの', '方法すべてに与える。', '', '仕様書は、規模や', '領域の異なるものを', '複数用意する。'], 16, gap=23)
    methods = [('方法1', BLUE, False, ['人間の設計者が、通常の方法で構成を検討する。']),
               ('方法2', BLUE, False, ['生成AIに要求仕様書を渡し、直接', 'アーキテクチャを提案させる。']),
               ('方法3', BLUE, False, ['要求間の関係グラフを構築し、', '構造分析を経て設計候補を生成する。']),
               ('追加', AMBER, True, ['方法2に、方法3で抽出した要求の', '関係を与える（原因の切り分け用）'])]
    for i, (tag, color, dash, lines) in enumerate(methods):
        y = 204 + i * 78
        f.rect(340, y, 440, 64, stroke=color, rx=12, dash=dash)
        f.text(356, y + 38 if len(lines) == 1 else y + 28, tag, 16, color, weight=700)
        if len(lines) == 1:
            f.text(412, y + 38, lines[0], 16, INK)
        else:
            f.para(412, y + 28, 356, lines, 16, gap=22)
        f.line(290, y + 32, 340, y + 32, color=BLUE, width=2.5, arrow=True)
        f.line(780, y + 32, 830, y + 32, color=BLUE, width=2.5, arrow=True)
    f.rect(830, 204, 320, 298, stroke=TEAL, rx=14)
    f.text(850, 238, '事前に固定する指標', 20, TEAL, weight=700)
    for i, s in enumerate(['要求の網羅性', '結合度（静的な測定値）', '変更の影響範囲', '説明可能性', '実装後の保守性', '設計時間']):
        f.circ(858, 270 + i * 28 - 5, 4, TEAL)
        f.text(872, 270 + i * 28, s, 17, INK)
    f.para(850, 450, 280, ['変更要求は事前に用意し、', '開始後に指標や重みは変えない。'], 14, MUTED, gap=19)
    cards = [(50, '試行条件を記録する', ['生成AIを使う方法は、同じ入力でも', '出力が変わり得る。モデルの種類と版、', '指示文、実行回数を記録し、', '結果のばらつきを示す。']),
             (422, '人間が盲検でレビューする', ['どの方法で作られた設計かを伏せ、', '複数の設計者が説明可能性や保守性を', '評価する。判断が割れた事実も記録', 'する。']),
             (794, '差の原因を切り分ける', ['方法3が優れていても、理由が関係', 'グラフの分割にあるのか、要求の丁寧', 'な抽出にあるのかはわからない。追加', 'の条件で原因を分けて確かめる。'])]
    for x, title, lines in cards:
        f.rect(x, 540, 356, 156, stroke=BLUE, rx=14)
        f.text(x + 18, 572, title, 18, BLUE, weight=700)
        f.para(x + 18, 602, 322, lines, 15, gap=22)
    f.footer('優位が示されなかった場合も、条件つきの結果として記録する。')
    return f.save()


FIGURES = [fig_1a, fig_1b, fig_2a, fig_2b, fig_2c, fig_3a, fig_3b, fig_3c, fig_4a, fig_4b, fig_4c]


def main() -> int:
    names = [draw() for draw in FIGURES]
    series = json.loads((ROOT / 'series.json').read_text(encoding='utf-8'))
    listed = [name for c in series['chapters'] for name in c.get('figures', [])]
    problems = []
    if listed != names:
        problems.append(f'series.json の figures と生成した図が一致しない: 生成={names} / 登録={listed}')
    stray = sorted(p.name for p in OUT.glob('*.svg') if p.name not in names)
    if stray:
        problems.append(f'生成対象に含まれないSVGがある: {stray}')
    print(json.dumps({'generated': len(names), 'problems': problems}, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
