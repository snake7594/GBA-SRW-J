# -*- coding: utf-8 -*-
"""부팅 저작권 화면 한글화: credits_ko.txt → IMG#15392 + SCR#15402 재생성

사용법:
  python credits_make.py <rom_in.gba> <rom_out.gba> [credits_ko.txt] [--font Galmuri9.ttf]
  python credits_make.py --preview [credits_ko.txt]   # PNG만 생성

구조(검증 완료):
  - IMG#15392: 32x14 = 448타일 풀 (타일0 = 공백)
  - SCR#15402: 30x20 풀스크린 타일맵, 타일번호 = 저장 인덱스 그대로(tw=32라 VRAM 변환이 항등)
  - 13줄, 줄 간격 12px(첫 줄 y=2). 글꼴 Galmuri9(size=10), 흰색 = 인덱스 1, 배경 = 13
렌더 규칙:
  - 줄 x는 중앙 정렬 후 8px 격자에 스냅 → 같은 y위상(12px 피치 → 2개 위상)의
    동일 문구(©, 반복 프리픽스)가 타일 단위로 중복제거되어 447타일 예산을 만족
"""
import sys, struct
from PIL import Image, ImageFont, ImageDraw
import scn_title_lib as L

IMG_I = 15392
SCR_I = 15402
LINE0_Y = 2
PITCH = 146 / 12  # 13줄, 마지막 줄 top = 148
BG = 13
INK = 1   # 인게임 팔레트는 1=흰색(몸통), 11~12=가장 어두움 (추출 팔레트와 반전)


def load_lines(path):
    lines = []
    for ln in open(path, encoding='utf-8'):
        ln = ln.rstrip('\n')
        if ln.startswith('#') or not ln.strip():
            continue
        lines.append(ln)
    return lines


def render_screen(lines, fontp):
    font = ImageFont.truetype(fontp, 10)  # Galmuri9는 PIL에서 size=10이 비트맵 정합
    S = [[0] * 240 for _ in range(160)]
    for i, text in enumerate(lines):
        # 한 줄 렌더 (자동 압축: 자간/공백 축소)
        for squeeze in (0, 1):
            im = Image.new('L', (400, 16), 0)
            dr = ImageDraw.Draw(im)
            x = 4
            for ch in text:
                if ch == ' ':
                    x += 4 - squeeze
                    continue
                dr.text((x, 3), ch, font=font, fill=255)
                adv = max(3, int(dr.textlength(ch, font=font)))
                x += max(1, adv - squeeze)
            bb = im.getbbox()
            if bb and bb[2] - bb[0] <= 236:
                break
        if not bb:
            continue
        crop = im.crop(bb)
        gw, gh = crop.size
        if gw > 240:
            raise ValueError(f'줄 {i+1} 폭 초과({gw}px): {text}')
        x0 = ((240 - gw) // 2) // 8 * 8  # 8px 격자 스냅(타일 중복제거 극대화)
        y0 = LINE0_Y + round(i * PITCH)
        cp = crop.load()
        for yy in range(gh):
            for xx in range(gw):
                if cp[xx, yy] >= 128 and 0 <= y0 + yy < 160:
                    S[y0 + yy][x0 + xx] = INK
    return S


def _hflip(b): return tuple(b[y * 8 + (7 - x)] for y in range(8) for x in range(8))
def _vflip(b): return tuple(b[(7 - y) * 8 + x] for y in range(8) for x in range(8))


def insert(rom_ba, S):
    img, *_ = L.ecd_decode(bytes(rom_ba), IMG_I)
    tw, th = img[5], img[6]
    cap = tw * th - 1
    scrd, *_ = L.ecd_decode(bytes(rom_ba), SCR_I)
    w, h = scrd[5], scrd[6]
    # 셀 수집 (잉크 셀: 배경 13으로 채움)
    lut = {}; order = []; refs = {}
    for r in range(h):
        for c in range(w):
            blk = []
            ink = False
            for yy in range(8):
                for xx in range(8):
                    v = S[r * 8 + yy][c * 8 + xx]
                    blk.append(v if v else BG)
                    if v:
                        ink = True
            if not ink:
                continue
            blk = tuple(blk)
            if blk in lut:
                refs[(r, c)] = lut[blk]; continue
            hit = None
            for fb, hf, vf in ((_hflip(blk), 1, 0), (_vflip(blk), 0, 1), (_vflip(_hflip(blk)), 1, 1)):
                if fb in lut:
                    hit = (lut[fb][0], hf, vf); break
            if hit:
                refs[(r, c)] = hit; lut[blk] = hit
            else:
                k = len(order); order.append(blk)
                lut[blk] = (k, 0, 0); refs[(r, c)] = (k, 0, 0)
    if len(order) > cap:
        raise ValueError(f'타일 {len(order)} > 한도 {cap}: 글자를 줄이세요')
    tiles = bytearray(tw * th * 32)
    # 타일0 = 전부 배경(13)으로 채움(원본과 동일하게 빈칸 채움용)
    for t in range(tw * th):
        for k in range(32):
            tiles[t * 32 + k] = BG | (BG << 4)
    for k, blk in enumerate(order):
        p = [list(blk[y * 8:(y + 1) * 8]) for y in range(8)]
        L.tile_put(tiles, 1 + k, p)
    ents = [0] * (w * h)
    for (r, c), (k, hf, vf) in refs.items():
        ents[r * w + c] = (1 + k) | (hf << 10) | (vf << 11)
    u1, r1 = L.ecd_write(rom_ba, IMG_I, L.img_build(tw, th, tiles), 8)
    u2, r2 = L.ecd_write(rom_ba, SCR_I, L.scr_build(w, h, ents), 8)
    return len(order), cap, u1, r1, u2, r2


def main():
    if '--preview' in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith('--')]
        table = args[0] if args else 'credits_ko.txt'
        S = render_screen(load_lines(table), 'Galmuri9.ttf')
        im = Image.new('RGB', (240, 160), (0, 0, 0))
        px = im.load()
        for y in range(160):
            for x in range(240):
                if S[y][x]:
                    px[x, y] = (232, 232, 224)
        im.save('credits_preview.png')
        print('credits_preview.png 저장')
        return
    rom_in, rom_out = sys.argv[1], sys.argv[2]
    table = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 'credits_ko.txt'
    fontp = 'Galmuri9.ttf'
    if '--font' in sys.argv:
        fontp = sys.argv[sys.argv.index('--font') + 1]
    rom = bytearray(open(rom_in, 'rb').read())
    S = render_screen(load_lines(table), fontp)
    n, cap, u1, r1, u2, r2 = insert(rom, S)
    open(rom_out, 'wb').write(rom)
    print(f'타일 {n}/{cap}, IMG {u1}B{"(재배치)" if r1 else ""}, SCR {u2}B{"(재배치)" if r2 else ""}')
    print('저장:', rom_out)


if __name__ == '__main__':
    main()
