# -*- coding: utf-8 -*-
"""한글 시나리오 제목 렌더러: titles_ko.txt → 편집용 캔버스 PNG 68장

사용법:
  python make_titles.py [titles_ko.txt] [출력폴더] [--font neodgm.ttf]

렌더 규칙:
  - Neo둥근모 16px (픽셀 폰트, 안티앨리어스 없음), 본문 흰색 + 1px 검정 외곽선
  - 1행(제N화) = 캔버스 y0~15 중앙, 2행 = y32~47 중앙, 3행 = y48~63 중앙
  - 한 줄 최대 232px. 초과 시 글자 간격을 1px씩 줄여(최대 -2) 자동 압축
"""
import sys, os
from PIL import Image, ImageDraw, ImageFont

MAXW = 232


def render_line(text, font):
    """텍스트 → (이진 잉크 마스크 Image('1' 유사 L), 폭, 높이). 자동 압축 포함."""
    for squeeze in (0, 1, 2):
        im = Image.new('L', (480, 32), 0)
        dr = ImageDraw.Draw(im)
        x = 8
        for ch in text:
            if ch == ' ':
                x += max(4, 8 - squeeze * 2)
                continue
            ox = -8 if ch == '\u300c' else 0  # 「 잉크를 왼쪽 반각으로
            dr.text((x + ox, 8), ch, font=font, fill=255)
            adv = int(dr.textlength(ch, font=font))
            if ch in '\u300c\u300d':
                adv = 8  # 「」 반각 취급
            x += max(1, adv - squeeze)
        bb = im.getbbox()
        if bb is None:
            return None, 0, 0
        im = im.crop(bb)
        if im.size[0] <= MAXW - 2:
            break
    return im.point(lambda v: 255 if v >= 128 else 0), im.size[0], im.size[1]


def compose(mask):
    """잉크 마스크 → 외곽선 합성 RGBA (본문 255, 외곽선 17)"""
    w, h = mask.size
    out = Image.new('RGBA', (w + 2, h + 2), (0, 0, 0, 0))
    px = out.load()
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            if mp[x, y]:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        px[x + 1 + dx, y + 1 + dy] = (17, 17, 17, 255)
    for y in range(h):
        for x in range(w):
            if mp[x, y]:
                px[x + 1, y + 1] = (255, 255, 255, 255)
    return out


def make_canvas(lines, font):
    canvas = Image.new('RGBA', (240, 64), (0, 0, 0, 0))
    bands = [(0, 16), (32, 48), (48, 64)]
    for i, text in enumerate(lines):
        if not text:
            continue
        mask, w, h = render_line(text, font)
        if mask is None:
            continue
        glyph = compose(mask)
        gw, gh = glyph.size
        if gw > 240:
            raise ValueError(f'줄이 너무 깁니다({gw}px): {text}')
        y0, y1 = bands[i]
        if gh > y1 - y0:
            glyph = glyph.crop((0, (gh - (y1 - y0)) // 2, gw, (gh - (y1 - y0)) // 2 + (y1 - y0)))
            gh = y1 - y0
        x = (240 - gw) // 2
        if i == 0 or True:
            x = max(0, (x - 1) // 8 * 8 + 1)  # 외곽선 1px 감안 8px 격자 정렬(셀 절약)
        y = y0 + (y1 - y0 - gh) // 2
        canvas.alpha_composite(glyph, (x, y))
    return canvas


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    table = args[0] if len(args) > 0 else 'titles_ko.txt'
    outdir = args[1] if len(args) > 1 else '시나리오제목_한글'
    fontp = 'neodgm.ttf'
    if '--font' in sys.argv:
        fontp = sys.argv[sys.argv.index('--font') + 1]
    font = ImageFont.truetype(fontp, 16)
    os.makedirs(outdir, exist_ok=True)
    for line in open(table, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('|')
        n = int(parts[0])
        lines = parts[1:4]
        canvas = make_canvas(lines, font)
        fn = os.path.join(outdir, f'e{n:02d}_img{3462 + n:05d}.png')
        canvas.save(fn)
        print(fn, '|'.join(lines))


if __name__ == '__main__':
    main()
