#!/usr/bin/env python3
"""Build a reflowable (text) EPUB from MinerU pipeline output.

Usage: reflow_epub.py OUT.epub CHUNK_DIR [CHUNK_DIR ...]
Each CHUNK_DIR is a MinerU output dir (contains *_middle.json) whose name ends
with _<first PDF page index> (0-based), e.g. build/mineru/p015.
"""
import glob, html, unicodedata, io, json, os, re, sys, uuid, zipfile, datetime
import numpy as np, pymupdf
from PIL import Image, ImageOps

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SRC = [os.path.join(REPO, f) for f in sorted(os.listdir(REPO)) if f.endswith('.pdf')][0]
TITLE = '数字设计和计算机体系结构（RISC-V版）'
AUTHORS = ['Sarah L. Harris', 'David Harris']
END_PUNCT = tuple('。！？；：:;!?」』”）)')

doc = pymupdf.open(SRC)
_ocr = None


def ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


_page_cache = {}


def page_image(pno):
    if pno not in _page_cache:
        _page_cache.clear()
        pg = doc[pno]
        x = pg.get_images(full=True)[0][0]
        im = Image.open(io.BytesIO(doc.extract_image(x)['image'])).convert('L')
        _page_cache[pno] = im
    return _page_cache[pno]


def crop(pno, bbox, size, pad=2):
    im = page_image(pno)
    sx, sy = im.width / size[0], im.height / size[1]
    x0, y0, x1, y1 = bbox
    box = (max(0, int((x0 - pad) * sx)), max(0, int((y0 - pad) * sy)),
           min(im.width, int((x1 + pad) * sx)), min(im.height, int((y1 + pad) * sy)))
    return im.crop(box)


def reocr(pno, span, size):
    """PaddleOCR v5 (used by MinerU) drops characters on this scan; re-read with PP-OCRv4."""
    old = span.get('content', '')
    if not old.strip():
        return old
    im = crop(pno, span['bbox'], size, pad=1).convert('RGB')
    if im.width < 4 or im.height < 4:
        return old
    res, _ = ocr()(np.array(im), use_det=False, use_cls=False, use_rec=True)
    if not res:
        return old
    new, score = res[0][0], float(res[0][1])
    if score < 0.75 or len(new) < len(old) * 0.9 or len(new) > len(old) * 1.6 + 3:
        return old
    # keep spaces that MinerU found between latin words
    return merge_spaces(old, new)


def merge_spaces(old, new):
    o = old.replace(' ', '')
    if o == new.replace(' ', ''):
        return old
    return new


try:
    import wordninja
except ImportError:
    wordninja = None


RU = '输进加写读引插深嵌转存接投陷流导收纳放填键移注代汇融混落'
def fix_ocr(t):
    t = ''.join(unicodedata.normalize('NFKC', ch) if '\u2e80' <= ch <= '\u2fdf' else ch for ch in t)
    t = re.sub('([' + RU + '])人', r'\1入', t)
    return t.replace('人口调查', '人口调查')


def fix_latin(t):
    t = fix_ocr(t)
    t = re.sub(r'(?<=[a-z]{2})(?=[A-Z][a-z])', ' ', t)
    if wordninja:
        def rep(m):
            w = m.group(0)
            parts = wordninja.split(w)
            if len(parts) > 1 and all(len(p) > 1 for p in parts) and ''.join(parts) == w:
                return ' '.join(parts)
            return w
        t = re.sub(r'(?<![A-Za-z_])[a-z]{9,}(?![A-Za-z_\d(])', rep, t)
    t = re.sub(r'([\u4e00-\u9fff（，。])\s+(?=[\u4e00-\u9fff])', r'\1', t)
    return t


# ---------- math ----------
from latex2mathml.converter import convert as l2m


def clean_tex(t):
    t = t.strip()
    # MinerU emits spaced digits: "1 0 1 1 0 _ { 2 }"
    t = re.sub(r'(?<=\d) (?=\d)', '', t)
    t = re.sub(r'(?<=\d) (?=\d)', '', t)
    t = re.sub(r'(?<=\d) \. (?=\d)', '.', t)
    t = re.sub(r'\\tag\s*\{[^}]*\}', '', t)
    return t


SIMPLE = re.compile(r'^[A-Za-z0-9.,+\-=<>/()\[\]|~ \\{}_^\']*$')
CMD = {r'\times': '×', r'\cdot': '·', r'\leqslant': '≤', r'\leq': '≤', r'\le': '≤', r'\geqslant': '≥',
       r'\geq': '≥', r'\ge': '≥', r'\neq': '≠', r'\sim': '～', r'\approx': '≈', r'\pm': '±', r'\to': '→',
       r'\rightarrow': '→', r'\infty': '∞', r'\ldots': '…', r'\cdots': '⋯', r'\mu': 'μ', r'\pi': 'π',
       r'\Omega': 'Ω', r'\alpha': 'α', r'\beta': 'β', r'\Delta': 'Δ', r'\%': '%', r'\#': '#', r'\&': '&amp;',
       r'\oplus': '⊕', r'\bullet': '•', r'\prime': '′', r'\lbrace': '{', r'\rbrace': '}', r'\,': ' ',
       r'\;': ' ', r'\quad': ' ', r'\ ': ' ', r'\{': '{', r'\}': '}', r'\log': 'log', r'\sum': '∑'}


FONT = {'mathrm', 'mathsf', 'textrm', 'text', 'mathtt', 'operatorname', 'mathbf', 'boldsymbol', 'pmb',
        'mathit', 'mathbb', 'mathfrak', 'mathcal', 'mathscr', 'textbf', 'textit', 'texttt', 'mathord', 'mathbin',
        'mathrel', 'mbox', 'textsf'}
SWITCH = {'tt', 'sf', 'bf', 'rm', 'it', 'cal', 'scriptstyle', 'displaystyle', 'textstyle', 'left', 'right',
          'big', 'Big', 'bigl', 'bigr', 'mathopen', 'mathclose', 'nolimits', 'limits'}
EXTRA = {'imath': 'i', 'jmath': 'j', 'textmu': 'μ', 'cap': '∩', 'cup': '∪', 'neg': '¬', 'lnot': '¬',
         'wedge': '∧', 'vee': '∨', 'land': '∧', 'lor': '∨', 'perp': '⊥', 'circ': '∘', 'div': '÷', 'mp': '∓',
         'Leftarrow': '⇐', 'Rightarrow': '⇒', 'leftarrow': '←', 'uparrow': '↑', 'downarrow': '↓',
         'lambda': 'λ', 'sigma': 'σ', 'tau': 'τ', 'theta': 'θ', 'phi': 'φ', 'epsilon': 'ε', 'varepsilon': 'ε',
         'gamma': 'γ', 'delta': 'δ', 'omega': 'ω', 'rho': 'ρ', 'eta': 'η', 'Sigma': 'Σ', 'Pi': 'Π', 'Phi': 'Φ',
         'ell': 'ℓ', 'star': '*', 'ast': '*', 'mid': '|', 'vert': '|', 'lvert': '|', 'rvert': '|', 'langle': '⟨',
         'rangle': '⟩', 'lfloor': '⌊', 'rfloor': '⌋', 'lceil': '⌈', 'rceil': '⌉', 'colon': ':', 'dots': '…',
         'emptyset': '∅', 'in': '∈', 'forall': '∀', 'exists': '∃', 'equiv': '≡', 'propto': '∝', 'partial': '∂',
         'nabla': '∇', 'degree': '°', 'textdegree': '°', 'checkmark': '✓', 'surd': '√', 'lt': '<', 'gt': '>',
         'textless': '<', 'textgreater': '>', 'mathrm{-}': '−', 'minus': '−', 'backslash': '\\', '_': '_'}
for _k, _v in list(CMD.items()):
    EXTRA.setdefault(_k[1:], _v)
SYM = {'&amp;': '&'}


def tex_simple(t, depth=0):
    """Convert simple inline TeX to HTML (sub/sup/overline); None if too complex."""
    s = t
    out = []
    i = 0
    n = len(s)

    def group(i):
        while i < n and s[i] == ' ':
            i += 1
        if i < n and s[i] == '{':
            d = 1; j = i + 1
            while j < n and d:
                d += {'{': 1, '}': -1}.get(s[j], 0); j += 1
            return s[i + 1:j - 1], j
        if i < n and s[i] == '\\':
            m = re.match(r'\\([A-Za-z]+|.)', s[i:])
            return s[i:i + m.end()], i + m.end()
        return (s[i], i + 1) if i < n else ('', i)

    while i < n:
        c = s[i]
        if c == '\\':
            m = re.match(r'\\([A-Za-z]+|.)', s[i:])
            cmd = m.group(1); i += m.end()
            if cmd in FONT:
                g, i = group(i)
                r = tex_simple(g, depth + 1)
                if r is None:
                    return None
                out.append(r)
            elif cmd in ('overline', 'bar'):
                g, i = group(i)
                r = tex_simple(g, depth + 1)
                if r is None:
                    return None
                out.append(f'<span class="ov">{re.sub(r" (?![^<]*>)", "", r)}</span>')
            elif cmd in SWITCH:
                continue
            elif cmd in EXTRA:
                v = EXTRA[cmd]
                out.append(f' {html.escape(v, quote=False)} ' if v in '∩∪∧∨⊕→⇒≈≡≤≥≠×÷±' else html.escape(html.unescape(v), quote=False))
            elif cmd in (',', ';', ' ', 'quad', 'qquad', '!', ':'):
                out.append(' ')
            elif cmd in '{}%#&$':
                out.append(html.escape(cmd, quote=False))
            else:
                return None
            continue
        if c in '_^':
            g, i = group(i + 1)
            r = tex_simple(g, depth + 1)
            if r is None or '<sub>' in r or '<sup>' in r:
                return None
            tag = 'sub' if c == '_' else 'sup'
            out.append(f'<{tag}>{re.sub(r" (?![^<]*>)", "", r)}</{tag}>')
            continue
        if c in '{} ':
            i += 1; continue
        if c.isalpha() and c.isascii():
            j = i
            while j < n and s[j].isalpha() and s[j].isascii():
                j += 1
            w = s[i:j]
            out.append(w if w in ('log', 'max', 'min', 'mod', 'sin', 'cos', 'exp') or len(w) > 2 else f'<i>{w}</i>')
            i = j; continue
        if c in '=+<>':
            lead = not ''.join(out).strip()
            out.append(html.escape(c, quote=False) if lead and c == '+' else f' {html.escape(c, quote=False)} ')
        elif c == '-':
            out.append('−')
        else:
            out.append(html.escape(c, quote=False))
        i += 1
    r = ''.join(out)
    r = r.replace('</i><i>', '')
    if depth == 0:
        m = re.fullmatch(r'\s*<su[bp]>(.*)</su[bp]>\s*', r)
        if m and '<' not in m.group(1):
            r = m.group(1)
    return re.sub(r'\s{2,}', ' ', r).strip() if depth == 0 else r


def mathml(t, display):
    try:
        m = l2m(t, display='block' if display else 'inline')
    except Exception:
        return None
    for _ in range(3):
        m = re.sub(r'<mi>\s*(<mrow>.*?</mrow>)\s*</mi>', r'\1', m)
    if re.search(r'<m[ino](?:\s[^>]*)?>\s*<', m):
        return None
    return m.replace('<math ', '<math xmlns="http://www.w3.org/1998/Math/MathML" ', 1) if 'xmlns=' not in m else m


def inline_math(t):
    t = clean_tex(t)
    h = tex_simple(t)
    if h is not None:
        return h
    return mathml(t, False) or html.escape(t)


def display_math(t):
    t = clean_tex(t)
    h = tex_simple(t)
    if h is not None and len(h) < 60:
        return f'<p class="eq">{h}</p>'
    m = mathml(t, True)
    return f'<div class="eq">{m}</div>' if m else f'<p class="eq">{html.escape(t)}</p>'


# ---------- blocks ----------
BULLET = re.compile(r'^\s*(?:[●•·▪■◆]|\\bullet|\(\s*[a-z]\s*[)）]|（\s*[a-z]\s*[)）]|\d+\.\d+(?!\.\d)(?=\s*[\u4e00-\u9fff(（A-Za-z“"]))')


def spans_html(lines, pno, size, do_ocr=True, split_items=False):
    parts = []
    for li, l in enumerate(lines):
        first = ''.join(x.get('content', '') for x in l['spans'][:2])
        if split_items and li and BULLET.match(first):
            parts.append(('br', ''))
        elif li:
            parts.append(('nl', ''))
        for s in l['spans']:
            if s['type'] == 'text':
                t = reocr(pno, s, size) if do_ocr else s.get('content', '')
                parts.append(('t', t))
            elif s['type'] == 'inline_equation':
                parts.append(('m', s.get('content', '')))
            elif s['type'] == 'interline_equation':
                parts.append(('M', s.get('content', '')))
    out = []
    for k, v in parts:
        if k == 't':
            out.append(html.escape(fix_latin(v), quote=False))
        elif k == 'm':
            out.append(inline_math(v))
        elif k == 'br':
            out.append('\x02')
        elif k == 'nl':
            out.append('\x03')
        else:
            out.append(display_math(v))
    h = ''.join(out)
    h = re.sub(r'(?<=[A-Za-z0-9,.;:!?)])\s*\x03\s*(?=[A-Za-z(])', ' ', h).replace('\x03', '')
    h = re.sub(r'(^|\x02)\s*(?:[●•·▪■◆]|\\bullet|<i>bullet</i>)\s*', r'\1• ', h)
    h = re.sub(r'(^|\x02)\s*[（(]\s*([a-z])\s*[)）]\s*', r'\1(\2) ', h)
    h = re.sub(r'(^|\x02)(\d+\.\d+)(?=[^\d.\s])', r'\1\2 ', h)
    return h


def block_text(b):
    return ''.join(s.get('content', '') for l in b.get('lines', []) for s in l['spans'])


def norm_title(t):
    t = t.strip()
    t = re.sub(r'^(第\s*\d+\s*章)\s*', r'\1 ', t)
    t = re.sub(r'^((?:\d+|[A-D])(?:\.\d+)+)\s*', r'\1 ', t)
    t = re.sub(r'^(附录\s*[A-D])\s*', r'\1 ', t)
    t = re.sub(r'^(\d+)\.\s*(?=\D)', r'\1. ', t)
    return t


def title_level(t):
    if re.match(r'^(第\s*\d+\s*章|附录\s*[A-D])', t):
        return 1
    m = re.match(r'^(?:\d+|[A-D])((?:\.\d+)+)', t)
    if m:
        return min(1 + m.group(1).count('.'), 4)
    if re.match(r'^\d+\.\s*\D', t):
        return 4
    return 2 if t in ('习题', '面试题', '本章总结') else 3


class Book:
    def __init__(self):
        self.items = []  # (kind, html, page, extra)
        self.images = {}

    def add(self, kind, h, pno, **kw):
        self.items.append(dict(kind=kind, html=h, page=pno, **kw))

    def image(self, pno, bbox, size, split=False):
        im = crop(pno, bbox, size, pad=3)
        im = ImageOps.autocontrast(im, cutoff=1)
        self.last_split = False
        if split:
            im2 = split_columns(im)
            if im2 is not None:
                im = im2
                self.last_split = True
        self.last_frac = im.width / page_image(pno).width
        if im.width > 1000:
            im = im.resize((1000, round(im.height * 1000 / im.width)), Image.LANCZOS)
        name = f'p{pno + 1:03d}_{len(self.images):04d}.png'
        buf = io.BytesIO()
        im.quantize(16).save(buf, 'PNG', optimize=True)
        self.images[name] = (buf.getvalue(), im.size)
        return name


def split_columns(im):
    """Stack a two-column code listing (high-level | assembly) vertically for narrow screens."""
    a = np.asarray(im, dtype=np.float32)
    h, w = a.shape
    d = a < 140
    rows = d.mean(axis=1) < 0.3  # drop horizontal rules
    dark = d[rows].sum(axis=0)
    lo, hi = int(w * 0.3), int(w * 0.7)
    best, run, start, bstart = 0, 0, 0, 0
    for x in range(lo, hi):
        if dark[x] <= 1:
            if run == 0:
                start = x
            run += 1
            if run > best:
                best, bstart = run, start
        else:
            run = 0
    if best < w * 0.02:
        return None
    cut = bstart + best // 2
    def trim(x0, x1):
        cols = np.where(dark[x0:x1] > 0)[0]
        if len(cols) == 0:
            return im.crop((x0, 0, x1, h))
        return im.crop((max(0, x0 + cols[0] - 6), 0, min(w, x0 + cols[-1] + 7), h))
    left, right = trim(0, cut), trim(cut, w)
    gap = 24
    out = Image.new('L', (max(left.width, right.width), h * 2 + gap), 255)
    out.paste(left, (0, 0))
    out.paste(right, (0, h + gap))
    for y in range(h + gap // 2 - 1, h + gap // 2 + 1):
        for x in range(0, out.width, 6):
            out.putpixel((x, y), 170)
    return out


def table_xhtml(h):
    h = re.sub(r'\s(rowspan|colspan)=1(?=[\s>])', '', h)
    h = re.sub(r'\s(rowspan|colspan)=(\d+)', r' \1="\2"', h)
    h = re.sub(r'<(/?)(th|td|tr|table|thead|tbody)\b([^>]*)>', r'<\1\2\3>', h)
    # escape stray text
    def esc(m):
        return '>' + html.escape(html.unescape(m.group(1)), quote=False) + '<'
    h = re.sub(r'>([^<]+)<', esc, h)
    return h


SKIP_CHAPTERS = ('封面', '目录')
_rng = os.environ.get('PAGES')  # optional 0-based inclusive range, e.g. 15-43


def keep_page(pno):
    if _rng:
        return any(int(r.split('-')[0]) <= pno <= int(r.split('-')[1]) for r in _rng.split(','))
    return True


def process_chunk(book, d):
    mid = glob.glob(os.path.join(d, '*_middle.json'))[0]
    start = int(re.search(r'(\d+)$', os.path.basename(os.path.dirname(mid)) if False else d.rstrip('/').split('/')[-1]).group(1))
    m = json.load(open(mid))
    for p in m['pdf_info']:
        pno = start + p['page_idx']
        if not keep_page(pno):
            continue
        size = p['page_size']
        for b in p['para_blocks']:
            t = b['type']
            if t in ('text', 'list', 'index', 'ref_text', 'phonetic', 'aside_text'):
                h = spans_html(b.get('lines', []) or [l for c in b.get('blocks', []) for l in c.get('lines', [])], pno, size, split_items=True)
                if '\x02' in h or re.match(r'^(• |\([a-z]\) |\d+\.\d+ )', h):
                    for k, part in enumerate(h.split('\x02')):
                        if part.strip():
                            book.add('p', part, pno, bbox=b['bbox'], indent=bool(re.match(r'^(• |\([a-z]\) |\d+\.\d+ )', part)), li=True)
                elif h.strip():
                    book.add('p', h, pno, bbox=b['bbox'], indent=_indent(b))
            elif t == 'title':
                txt = norm_title(spans_html(b['lines'], pno, size))
                book.add('h', txt, pno, level=title_level(re.sub('<[^>]+>', '', txt)))
            elif t == 'interline_equation':
                book.add('eq', ''.join(display_math(s.get('content', '')) for l in b['lines'] for s in l['spans']), pno)
            elif t in ('image', 'table', 'code', 'chart'):
                body, caps, notes = None, [], []
                for c in b['blocks']:
                    ct = c['type']
                    if ct.endswith('_caption'):
                        caps.append(spans_html(c['lines'], pno, size))
                    elif ct.endswith('_footnote'):
                        notes.append((c, spans_html(c['lines'], pno, size)))
                    elif ct.endswith('_body'):
                        body = c
                if body is None:
                    continue
                spans = [s for l in body.get('lines', []) for s in l['spans']]
                cap = '<br/>'.join(x for x in caps if x)
                plain_cap = re.sub('<[^>]+>', '', cap)
                if t == 'table' and plain_cap.startswith('表') and spans and spans[0].get('html') and len(spans[0]['html']) > 20:
                    book.add('table', table_xhtml(spans[0]['html']), pno, cap=cap)
                elif t == 'code':
                    code = '\n'.join(s.get('content', '') for s in spans)
                    book.add('code', html.escape(code, quote=False), pno, cap=cap)
                else:
                    name = book.image(pno, body['bbox'], size, split=plain_cap.startswith('代码示例'))
                    frac = (body['bbox'][2] - body['bbox'][0]) / size[0]
                    if book.last_split:
                        frac = book.last_frac
                    book.add('fig', name, pno, cap=cap, frac=frac)
                for c, h in notes:
                    if h.strip():
                        book.add('p', h, pno, bbox=c['bbox'], indent=False, note=True)


def _indent(b):
    ls = b.get('lines') or []
    if not ls:
        return False
    return ls[0]['bbox'][0] - b['bbox'][0] > 8


def merge_paragraphs(items):
    out = []
    pending = []  # floats (figs/tables) encountered while a paragraph is still open
    for it in items:
        if it['kind'] == 'p' and not it.get('note'):
            last = next((o for o in reversed(out) if o['kind'] == 'p'), None) if not pending or True else None
            prev = out[-1] if out else None
            open_p = None
            if prev is not None and prev['kind'] == 'p' and not prev.get('note'):
                open_p = prev
            elif pending and out and out[-1]['kind'] == 'p':
                open_p = out[-1]
            starts_new = re.match(r'^(<b>)?(例\s*\d|解[:：]|• |\([a-z]\) )', it['html'])
            if open_p is not None and not open_p['plain'].endswith(END_PUNCT) and not it['indent'] and not starts_new:
                open_p['html'] += it['html']
                open_p['plain'] += re.sub('<[^>]+>', '', it['html'])
                continue
            out.extend(pending); pending = []
            it['plain'] = re.sub('<[^>]+>', '', it['html']).rstrip()
            out.append(it)
        elif it['kind'] in ('fig', 'table', 'code', 'eq') and out and out[-1]['kind'] == 'p' \
                and not out[-1]['plain'].endswith(END_PUNCT) and it['kind'] != 'eq':
            pending.append(it)
        else:
            out.extend(pending); pending = []
            if it['kind'] == 'p':
                it['plain'] = re.sub('<[^>]+>', '', it['html']).rstrip()
            out.append(it)
    out.extend(pending)
    return out


CSS = '''
body{margin:0 0.4em;font-family:serif;line-height:1.75;text-align:justify}
h1{font-size:1.5em;text-align:center;margin:1.2em 0 1em;line-height:1.4}
h2{font-size:1.25em;margin:1.4em 0 .6em;line-height:1.4;border-bottom:1px solid #999;padding-bottom:.15em}
h3{font-size:1.1em;margin:1.2em 0 .5em;line-height:1.4}
h4{font-size:1em;margin:1em 0 .4em}
p{margin:0 0 .3em;text-indent:2em}
p.ex{text-indent:0;margin-top:.6em}
p.ex b{color:#1a4f8b}
p.li{text-indent:-1.2em;margin-left:1.2em}
p.note{text-indent:0;font-size:.92em}
.eq{text-align:center;text-indent:0;margin:.6em 0}
figure{margin:1em 0;text-align:center}
figure img{max-width:100%;height:auto}
figcaption,.cap{overflow-wrap:anywhere;word-break:break-word;font-size:.85em;color:#444;text-align:center;text-indent:0;margin:.3em 0 .8em;line-height:1.4}
.tw{overflow-x:auto;margin:.8em 0}
table{border-collapse:collapse;margin:0 auto;font-size:.8em;line-height:1.35}
td,th{border:1px solid #888;padding:.15em .35em;text-align:center}
pre{font-family:monospace;font-size:.8em;line-height:1.4;white-space:pre-wrap;word-wrap:break-word;background:#f4f4f4;padding:.5em;border-radius:3px}
.ov{text-decoration:overline}
i{font-family:serif}
'''


def render(items):
    hs = []
    for it in items:
        k = it['kind']
        if it.get('cap'):
            it['cap'] = fix_ocr(it['cap'])
        if k == 'h':
            lv = it['level']
            hs.append(f'<h{lv}>{it["html"]}</h{lv}>')
        elif k == 'p':
            h = fix_ocr(it['html'])
            cls = ''
            if it.get('note'):
                cls = ' class="note"'
            elif it.get('li'):
                cls = ' class="li"'
            m = re.match(r'^(例\s*\d+\.\d+)', it.get('plain', ''))
            if m:
                cls = ' class="ex"'
                h = re.sub(r'^(例\s*\d+\.\d+)', r'<b>\1</b>', h)
            hs.append(f'<p{cls}>{h}</p>')
        elif k == 'eq':
            hs.append(it['html'])
        elif k == 'fig':
            cap = f'<figcaption>{it["cap"]}</figcaption>' if it['cap'] else ''
            hs.append(f'<figure><img src="../images/{it["html"]}" alt="" style="width:{min(100, max(35, round(it["frac"] / 0.78 * 150)))}%"/>{cap}</figure>')
        elif k == 'table':
            cap = f'<p class="cap">{it["cap"]}</p>' if it['cap'] else ''
            hs.append(f'{cap}<div class="tw">{it["html"]}</div>')
        elif k == 'code':
            cap = f'<p class="cap">{it["cap"]}</p>' if it['cap'] else ''
            hs.append(f'{cap}<pre>{it["html"]}</pre>')
    return '\n'.join(hs)


def xhtml(title, body):
    return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head><meta charset="utf-8"/><title>{html.escape(title)}</title><link rel="stylesheet" type="text/css" href="../style.css"/></head>
<body>
{body}
</body></html>'''


def build(out, chunks):
    book = Book()
    for d in sorted(chunks, key=lambda d: int(re.search(r'(\d+)$', d.rstrip('/')).group(1))):
        print('chunk', d, flush=True)
        process_chunk(book, d)
    for it in book.items:
        if it['kind'] == 'fig':
            it['size'] = book.images[it['html']][1]
    items = merge_paragraphs(book.items)
    # split into chapters using the PDF outline
    tops = [(t, pg - 1) for lv, t, pg in doc.get_toc() if lv == 1 and t not in SKIP_CHAPTERS]
    def chap_of(pno):
        c = None
        for k, (t, st) in enumerate(tops):
            if st <= pno:
                c = k
        return c
    chaps, cur = [], None
    for it in items:
        k = chap_of(it['page'])
        if k is None:
            continue
        if cur is None or cur['k'] != k:
            t = re.sub(r'^(第\d+章|附录[A-D])\s*', r'\1 ', tops[k][0])
            cur = {'k': k, 'title': t, 'items': [dict(kind='h', html=html.escape(t), level=1, page=tops[k][1])], 'seen2': False}
            chaps.append(cur)
        if it['kind'] == 'h':
            plain = re.sub('<[^>]+>', '', it['html']).replace(' ', '')
            if it['level'] == 1 or (not cur['seen2'] and plain and plain in cur['title'].replace(' ', '')):
                continue
            if it['level'] == 2:
                cur['seen2'] = True
        cur['items'].append(it)
    files = []
    for i, c in enumerate(chaps):
        fn = f'c{i:02d}.xhtml'
        for j, it in enumerate(c['items']):
            if it['kind'] == 'h':
                it['id'] = f'h{i}_{j}'
                it['html'] = it['html']
        body = render(c['items'])
        # add ids to headings
        n = [0]
        heads = [it for it in c['items'] if it['kind'] == 'h']
        def addid(m):
            k = n[0]; n[0] += 1
            return f'<h{m.group(1)} id="{heads[k]["id"]}">'
        body = re.sub(r'<h([1-4])>', addid, body)
        files.append((fn, c['title'], xhtml(c['title'], body), heads))
    used = {k: v for k, v in book.images.items() if any(f'images/{k}"' in f[2] for f in files)}
    write_epub(out, files, used)


def write_epub(out, files, images):
    uid = 'urn:uuid:' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'book-for-study/reflow/' + TITLE))
    now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    man, spine, nav = [], [], []
    for fn, t, x, heads in files:
        props = ' properties="mathml"' if '<math' in x else ''
        man.append(f'<item id="{fn[:-6]}" href="text/{fn}" media-type="application/xhtml+xml"{props}/>')
        spine.append(f'<itemref idref="{fn[:-6]}"/>')
    pg = doc[0]
    cim = Image.open(io.BytesIO(doc.extract_image(pg.get_images(full=True)[0][0])['image'])).convert('RGB')
    cim.thumbnail((1000, 1400))
    cbuf = io.BytesIO()
    cim.save(cbuf, 'JPEG', quality=82)
    man.append('<item id="cover-img" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>')
    man.append('<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>')
    spine.insert(0, '<itemref idref="cover"/>')
    coverx = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head><meta charset="utf-8"/><title>封面</title><style>body{{margin:0;text-align:center}}img{{max-width:100%;max-height:100vh}}</style></head>
<body epub:type="cover"><img src="../images/cover.jpg" alt="封面"/></body></html>'''
    for k in images:
        man.append(f'<item id="i{k[:-4]}" href="images/{k}" media-type="image/png"/>')
    # nested nav: levels 1-2
    def navlist():
        h = ['<ol>']
        for fn, t, x, heads in files:
            top = [hd for hd in heads if hd['level'] == 1]
            href = f'text/{fn}'
            subs = [hd for hd in heads if hd['level'] == 2]
            h.append(f'<li><a href="{href}">{html.escape(t)}</a>')
            if subs:
                h.append('<ol>' + ''.join(f'<li><a href="{href}#{s["id"]}">{html.escape(re.sub("<[^>]+>", "", s["html"]))}</a></li>' for s in subs) + '</ol>')
            h.append('</li>')
        h.append('</ol>')
        return ''.join(h)
    navx = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head><meta charset="utf-8"/><title>目录</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><nav epub:type="toc" id="toc"><h1>目录</h1>{navlist()}</nav></body></html>'''
    authors = ''.join(f'<dc:creator id="a{i}">{a}</dc:creator>' for i, a in enumerate(AUTHORS))
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="zh-CN">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">{uid}</dc:identifier><dc:title>{TITLE}</dc:title>{authors}
<dc:contributor>张功萱 等（译）</dc:contributor><dc:language>zh-CN</dc:language>
<meta property="dcterms:modified">{now}</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="css" href="style.css" media-type="text/css"/>
{chr(10).join(man)}
</manifest>
<spine>{''.join(spine)}</spine>
</package>'''
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml', '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr('OEBPS/content.opf', opf)
        z.writestr('OEBPS/nav.xhtml', navx)
        z.writestr('OEBPS/style.css', CSS)
        z.writestr('OEBPS/text/cover.xhtml', coverx)
        z.writestr('OEBPS/images/cover.jpg', cbuf.getvalue())
        for fn, t, x, heads in files:
            z.writestr(f'OEBPS/text/{fn}', x)
        for k, (data, sz) in images.items():
            z.writestr(f'OEBPS/images/{k}', data)
    print('wrote', out, os.path.getsize(out) // 1024, 'KB')


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2:])
