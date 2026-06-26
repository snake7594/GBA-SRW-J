#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
슈퍼로봇대전 J (GBA) — 갈무리체 한글 폰트 채우기
=================================================

ROM 폰트 영역의 한자 글리프 슬롯을 완성형(KS X 1001) 한글 2350자로 교체한다.
첫 한자 슬롯(亜 = "아", 엔트리 0)부터 차례대로 가·각·간·… 순서로 채운다.
이는 EUC-KR 0xB0A1(가) ↔ SJIS 0x889F(亜) 1:1 대응 규칙과 일치한다.

각 엔트리의 22바이트 비트맵만 덮어쓰고 4바이트 마커·나머지 ROM은 보존한다.

폰트 구조: 0x1EF058부터 26바이트(마커4 + 비트맵22, 16×11 1bpp), 총 2965슬롯.
글리프: 갈무리11(11px) 렌더 → 밝기 128 임계값으로 1bpp 흑백화.

사용법:
  python3 fill_hangul_galmuri.py jp.gba out.gba
  python3 fill_hangul_galmuri.py jp.gba out.gba --font Galmuri11.ttf --size 11 --ox 1 --oy 0
"""
import sys, argparse
from PIL import Image, ImageFont, ImageDraw

FONT_BASE = 0x1EF058
FONT_END  = 0x201D7A
ENTRY     = 26
GW, GH    = 16, 11
COUNT     = (FONT_END - FONT_BASE) // ENTRY   # 2965


def ksx1001_hangul():
    """완성형(KS X 1001) 한글 2350자를 표준 순서로 생성."""
    out = []
    for lead in range(0xB0, 0xC9):            # 0xB0 ~ 0xC8 (25행)
        for trail in range(0xA1, 0xFF):       # 0xA1 ~ 0xFE (94자)
            out.append(bytes([lead, trail]).decode('euc-kr'))
    return out


def render_glyph(ch, font, ox, oy):
    """한 글자를 16×11 1bpp 비트맵(22바이트)으로."""
    im = Image.new('L', (GW, GH), 255)
    ImageDraw.Draw(im).text((ox, oy), ch, font=font, fill=0, anchor='la')
    px = im.load()
    bmp = bytearray(22)
    for y in range(GH):
        b0 = b1 = 0
        for x in range(GW):
            if px[x, y] < 128:                # 잉크
                if x < 8:
                    b0 |= 0x80 >> x
                else:
                    b1 |= 0x80 >> (x - 8)
        bmp[y * 2] = b0
        bmp[y * 2 + 1] = b1
    return bmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('out')
    ap.add_argument('--font', default='Galmuri11-Bold.ttf')
    ap.add_argument('--size', type=int, default=11)
    ap.add_argument('--ox', type=int, default=1)
    ap.add_argument('--oy', type=int, default=0)
    ap.add_argument('--start', type=int, default=0, help='시작 엔트리 인덱스')
    ap.add_argument('--chars', help='교체할 글자 파일(미지정 시 완성형 2350자 자동)')
    a = ap.parse_args()

    data = bytearray(open(a.rom, 'rb').read())
    font = ImageFont.truetype(a.font, a.size)

    if a.chars:
        chars = [c for c in open(a.chars, encoding='utf-8').read() if c.strip()]
    else:
        chars = ksx1001_hangul()

    n = len(chars)
    print(f'[*] 글자 {n}개, 시작 엔트리 {a.start}')
    print(f'    처음 20: {"".join(chars[:20])}')
    print(f'    마지막 20: {"".join(chars[-20:])}')
    if a.start + n > COUNT:
        sys.exit(f'[!] 슬롯 초과: {a.start}+{n} > {COUNT}')

    for i, ch in enumerate(chars):
        off = FONT_BASE + (a.start + i) * ENTRY + 4   # 마커 4바이트 보존
        data[off:off + 22] = render_glyph(ch, font, a.ox, a.oy)

    open(a.out, 'wb').write(data)
    print(f'[*] 엔트리 {a.start}~{a.start + n - 1} 교체 완료 → {a.out}')


if __name__ == '__main__':
    main()
