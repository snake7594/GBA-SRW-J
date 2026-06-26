#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
슈퍼로봇대전 J (GBA) — 개별 글리프 교체 도구 (반각 세로보존판)
=============================================================
폰트 영역에서 특정 일본어 글자(cp932)의 슬롯을 찾아
지정한 한글 글자의 비트맵으로 교체한다.

폰트 구조
---------
한자0 슬롯(亜 = cp932 0x889F)이 0x1EF058에 위치하며,
각 엔트리는 26바이트(마커 4 + 비트맵 22, 16×11 1bpp)다.
마커 = 빅엔디안 cp932 코드 + 0x0000.
가나·기호·한자가 같은 26바이트 그리드에 cp932 코드 순서로 연속 배치된다.
가타카나 ド(0x8368)도 같은 그리드(0x1E8B64)에 있다.

★ 반각(半角) 처리
-----------------
게임은 가타카나 슬롯을 화면에 '반각 폭(글자 간격 8px)'으로 출력한다.
(실측: ド 간격 8px, 한자/한글 간격 12px.)
한글을 보통 폭(11px)으로 넣으면 오른쪽이 다음 글자에 가려져 "왼쪽 반만" 보인다.

→ 해결: 전각과 동일한 크기(size 12)로 한글을 그려 '세로 높이를 전각과 똑같이' 만든 뒤,
   가로만 잉크 보존(max-pool) 방식으로 8px로 압축한다.
   - 세로 높이: 전각과 동일 (예: "도" y0~y9)
   - 가로 폭  : 8px (반각, x0~x7)
   - max-pool 압축이라 ㅗ 같은 1px 세로획도 보존됨(평균 압축은 가는 획이 사라짐).

  전각(한자 슬롯) : Galmuri11 size 12 / ox 1 / oy -1            폭 ~11px
  반각(가나 슬롯) : 위와 동일하게 렌더 후 → 가로 max-pool 8px   폭 8px / 세로 동일

전각/반각은 cp932 코드로 자동 판정(가타카나=반각). --full/--half로 강제 지정 가능.
교체 시 22바이트 비트맵만 덮어쓰고 4바이트 마커는 보존한다.

사용법
------
  # 기본: ド → 도 (가타카나라 자동 반각, 세로는 전각 높이)
  python3 patch_glyph.py in.gba out.gba

  # 여러 글자 (가나=자동 반각, 한자=자동 전각)
  python3 patch_glyph.py in.gba out.gba --map "ド=도,ガ=가,亜=아"

  # 반각 목표 폭 조정(기본 8). 7로 줄이면 더 여유, 9 이상은 잘릴 위험.
  python3 patch_glyph.py in.gba out.gba --hwidth 8

  # 자동판정 무시
  python3 patch_glyph.py in.gba out.gba --map "ド=도" --full "ド"
"""
import argparse
from PIL import Image, ImageFont, ImageDraw

ANCHOR = 0x1EF058   # 엔트리 0 = cp932 0x889F (亜)
ENTRY  = 26
GW, GH = 16, 11

# 가타카나(전각) cp932 영역 — 게임에서 반각 폭으로 출력됨
KATAKANA_LO, KATAKANA_HI = 0x8340, 0x8396


def find_slot(data, code):
    """cp932 코드(빅엔디안 마커)를 가진 폰트 슬롯의 비트맵 오프셋(마커 다음)을 반환."""
    hi, lo = code >> 8, code & 0xFF
    for k in range(-4000, 7000):                  # 가나/기호(음수) ~ 한자(양수)
        off = ANCHOR + k * ENTRY
        if off < 0 or off + ENTRY > len(data):
            continue
        if data[off] == hi and data[off + 1] == lo \
           and data[off + 2] == 0 and data[off + 3] == 0:
            return off + 4
    return None


def bit(bmp, x, y):
    return (((bmp[y * 2] >> (7 - x)) & 1) if x < 8
            else ((bmp[y * 2 + 1] >> (7 - (x - 8))) & 1))


def setbit(bmp, x, y):
    if x < 8:
        bmp[y * 2] |= 0x80 >> x
    else:
        bmp[y * 2 + 1] |= 0x80 >> (x - 8)


def ink_box(bmp):
    cols = [x for y in range(GH) for x in range(GW) if bit(bmp, x, y)]
    rows = [y for y in range(GH) for x in range(GW) if bit(bmp, x, y)]
    if not cols:
        return None
    return min(cols), max(cols), min(rows), max(rows)


def render_glyph(ch, font, ox, oy):
    """한 글자를 16×11 1bpp 비트맵(22바이트)으로."""
    im = Image.new('L', (GW, GH), 255)
    ImageDraw.Draw(im).text((ox, oy), ch, font=font, fill=0, anchor='la')
    px = im.load()
    bmp = bytearray(22)
    for y in range(GH):
        b0 = b1 = 0
        for x in range(GW):
            if px[x, y] < 128:
                if x < 8:
                    b0 |= 0x80 >> x
                else:
                    b1 |= 0x80 >> (x - 8)
        bmp[y * 2] = b0
        bmp[y * 2 + 1] = b1
    return bmp


def squash_width_maxpool(src, target_w):
    """가로만 target_w(px)로 압축(세로 유지). 잉크 보존(어느 입력열이든 켜져 있으면 출력 켜기)."""
    box = ink_box(src)
    if box is None:
        return bytearray(src)
    x0, x1, _, _ = box
    w = x1 - x0 + 1
    if w <= target_w:                              # 이미 충분히 좁으면 좌측 정렬만
        out = bytearray(22)
        for y in range(GH):
            for x in range(x0, x1 + 1):
                if bit(src, x, y):
                    setbit(out, x - x0, y)
        return out
    out = bytearray(22)
    for y in range(GH):
        for ox in range(target_w):
            ix_lo = x0 + ox * w // target_w
            ix_hi = x0 + (ox + 1) * w // target_w
            if ix_hi <= ix_lo:
                ix_hi = ix_lo + 1
            if any(bit(src, ix, y) for ix in range(ix_lo, min(ix_hi, GW))):
                setbit(out, ox, y)
    return out


def ascii_art(bmp):
    return [''.join('#' if bit(bmp, x, y) else '.' for x in range(GW)) for y in range(GH)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('out')
    ap.add_argument('--map', default='ド=도',
                    help='쉼표로 구분한 "일본어=한글" 매핑 (기본: ド=도)')
    ap.add_argument('--font', default='Galmuri11.ttf')
    # 렌더 파라미터 (전각/반각 공통 — 반각은 이걸로 그린 뒤 가로만 압축)
    ap.add_argument('--size', type=int, default=12)
    ap.add_argument('--ox',   type=int, default=1)
    ap.add_argument('--oy',   type=int, default=-1)
    ap.add_argument('--hwidth', type=int, default=8, help='반각 글자 목표 가로폭(px, 기본 8)')
    # 자동판정 강제 오버라이드
    ap.add_argument('--full', default='', help='강제로 전각 처리할 일본어 글자들(붙여서)')
    ap.add_argument('--half', default='', help='강제로 반각 처리할 일본어 글자들(붙여서)')
    ap.add_argument('--preview', action='store_true', help='교체 글리프 ASCII 미리보기')
    a = ap.parse_args()

    data = bytearray(open(a.rom, 'rb').read())
    font = ImageFont.truetype(a.font, a.size)
    force_full = set(a.full)
    force_half = set(a.half)

    pairs = []
    for item in a.map.split(','):
        item = item.strip()
        if not item:
            continue
        src, dst = item.split('=')
        pairs.append((src.strip(), dst.strip()))

    done = 0
    for src, dst in pairs:
        code = int.from_bytes(src.encode('cp932'), 'big')
        off = find_slot(data, code)
        if off is None:
            print(f'[!] {src!r}(0x{code:04X}) 슬롯을 못 찾음 — 건너뜀')
            continue

        if src in force_full:
            half = False
        elif src in force_half:
            half = True
        else:
            half = (KATAKANA_LO <= code <= KATAKANA_HI)

        glyph = render_glyph(dst, font, a.ox, a.oy)     # 전각 크기로 렌더(세로 높이 결정)
        if half:
            bmp = squash_width_maxpool(glyph, a.hwidth)  # 가로만 압축, 세로 유지
            mode = f'반각(가로{a.hwidth}px)'
        else:
            bmp = glyph
            mode = '전각'

        box = ink_box(bmp)
        lo, hi = (box[0], box[1]) if box else (None, None)
        top, bot = (box[2], box[3]) if box else (None, None)
        warn = '  ⚠ 폭 8px 초과(잘릴 수 있음)' if (half and hi is not None and hi > 7) else ''
        data[off:off + 22] = bmp
        done += 1
        print(f'[*] {src!r}(0x{code:04X}) @ 0x{off-4:06X} -> {dst!r} [{mode}] '
              f'가로 x{lo}~x{hi} 세로 y{top}~y{bot}{warn}')
        if a.preview:
            for line in ascii_art(bmp):
                print('    ' + line)

    open(a.out, 'wb').write(data)
    print(f'[*] {done}자 교체 완료 -> {a.out}')


if __name__ == '__main__':
    main()
