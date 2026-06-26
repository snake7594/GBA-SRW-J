# -*- coding: utf-8 -*-
"""시나리오 제목 삽입: 편집된 PNG → ROM (IMG 타일 + SCR 타일맵 동시 재생성)

사용법:
  python scn_title_insert.py <rom_in.gba> <rom_out.gba> <png폴더 또는 png파일...> [--grow]

규칙:
  - 파일명에서 화 번호 인식: e{NN}_*.png
  - 캔버스 240x64 RGBA, y0 = 화면 타일행 7
  - 알파<128 = 투명(색0). 그 외 = 밝기→인덱스(반전 팔레트): 흰 본문→1, 검정 외곽선→15
    (게임 제목 팔레트가 인덱스1=흰색, 인덱스15=검정이므로 밝을수록 낮은 인덱스로 환원)
  - 텍스트 줄은 2타일행 단위 정렬: (행7,8) (행9,10) (행11,12) (행13,14)
  - 비어있지 않은 8x8 셀 수 <= 타일수-1 (타일0은 항상 공백 = 빈칸 채움용)
    * --grow: 한도 초과 시 타일 수를 최대 95개(3행 한도)까지 확장 시도
  - 동일 셀은 타일 1개로 공유(중복 제거), 압축 결과가 슬롯에 들어가야 함(자동 검증)
"""
import sys, os, re, glob
from PIL import Image
import scn_title_lib as L


def png_to_cells(path):
    im = Image.open(path).convert('RGBA')
    if im.size != (240, L.CANVAS_ROWS * 8):
        raise ValueError(f'{path}: 크기 {im.size} != (240,{L.CANVAS_ROWS*8})')
    px = im.load()
    cells = {}  # (scr_row, col) -> 64바이트 인덱스 튜플
    for (ra, rb) in L.ROW_PAIRS:
        for r in (ra, rb):
            cy = r - L.CANVAS_ROW0
            for c in range(30):
                blk = []
                ink = False
                for yy in range(8):
                    for xx in range(8):
                        pr, pg, pb, pa = px[c * 8 + xx, cy * 8 + yy]
                        if pa < 128:
                            blk.append(0)
                        else:
                            g = (pr * 299 + pg * 587 + pb * 114) // 1000
                            v = max(1, min(15, round(g / 17)))
                            # 제목 화면 팔레트는 반전형이다(전 화 PLT#3530 계열:
                            # 인덱스1=흰색, 인덱스15=검정). 밝을수록 낮은 인덱스로 환원해야
                            # 게임에서 흰 본문/검정 외곽선으로 보인다. (16-v: 흰255→1, 검17→15)
                            blk.append(16 - v)
                            ink = True
                if ink:
                    cells[(r, c)] = tuple(blk)
    return cells


def _hflip(blk):
    return tuple(blk[y * 8 + (7 - x)] for y in range(8) for x in range(8))


def _vflip(blk):
    return tuple(blk[(7 - y) * 8 + x] for y in range(8) for x in range(8))


def insert_ep(rom_ba, n, cells, grow=False):
    ii, si = L.EP_IMG0 + n, L.EP_SCR0 + n
    img, *_ = L.ecd_decode(bytes(rom_ba), ii)
    scrd, *_ = L.ecd_decode(bytes(rom_ba), si)
    tw, th, _ = L.img_parse(img)
    w, h, _ = L.scr_parse(scrd)

    # 플립 인식 중복 제거 후 타일 할당
    lut = {}    # blk -> (타일순번k, hf, vf)
    order = []  # 고유 블록 목록
    refs = {}   # (r,c) -> (k, hf, vf)
    for key in sorted(cells):
        blk = cells[key]
        if blk in lut:
            refs[key] = lut[blk]
            continue
        hb, vb = _hflip(blk), _vflip(blk)
        hvb = _vflip(hb)
        hit = None
        if hb in lut:
            k, _, _ = lut[hb]; hit = (k, 1, 0)
        elif vb in lut:
            k, _, _ = lut[vb]; hit = (k, 0, 1)
        elif hvb in lut:
            k, _, _ = lut[hvb]; hit = (k, 1, 1)
        if hit:
            refs[key] = hit
            lut[blk] = hit
        else:
            k = len(order)
            order.append(blk)
            lut[blk] = (k, 0, 0)
            refs[key] = (k, 0, 0)
    need = len(order)
    cap = tw * th - 1
    if need > cap:
        if not grow:
            raise ValueError(f'e{n:02d}: 잉크 셀 {need} > 한도 {cap}. 글자를 줄이거나 --grow 사용')
        # 행 수(최대 3행 = 게임 검증 한도) → 폭(최대 32 = VRAM 행) 순으로 확장
        ok = False
        for ntw in [tw] + list(range(tw + 1, 33)):
            for nth in range(th, 4):
                if ntw * nth - 1 >= need:
                    tw, th = ntw, nth
                    ok = True
                    break
            if ok:
                break
        cap = tw * th - 1
        if need > cap:
            raise ValueError(f'e{n:02d}: 잉크 셀 {need} > 최대 한도 {cap}(=32x3-1)')
    ntiles = tw * th
    tiles = bytearray(ntiles * 32)
    for k, blk in enumerate(order):
        s = 1 + k
        p = [list(blk[y * 8:(y + 1) * 8]) for y in range(8)]
        L.tile_put(tiles, s, p)

    ents = [0] * (w * h)
    for (r, c), (k, hf, vf) in refs.items():
        s = 1 + k
        ents[r * w + c] = L.storage_to_vram(s, tw) | (hf << 10) | (vf << 11)

    used_img, ri = L.ecd_write(rom_ba, ii, L.img_build(tw, th, tiles), 8)
    used_scr, rs = L.ecd_write(rom_ba, si, L.scr_build(w, h, ents), 8)
    return need, ntiles, used_img, used_scr, ('IMG재배치' if ri else '') + ('SCR재배치' if rs else '')


def main():
    rom_in, rom_out = sys.argv[1], sys.argv[2]
    grow = '--grow' in sys.argv
    args = [a for a in sys.argv[3:] if not a.startswith('--')]
    pngs = []
    for a in args:
        if os.path.isdir(a):
            pngs += glob.glob(os.path.join(a, 'e*_img*.png'))
        else:
            pngs.append(a)
    rom_ba = bytearray(open(rom_in, 'rb').read())
    for p in sorted(pngs):
        m = re.search(r'e(\d{2})_', os.path.basename(p))
        if not m:
            print(f'건너뜀(이름 형식 불일치): {p}')
            continue
        n = int(m.group(1))
        cells = png_to_cells(p)
        need, ntiles, ui, us, note = insert_ep(rom_ba, n, cells, grow)
        print(f'e{n:02d}: 셀 {need}/{ntiles - 1}, IMG {ui}B, SCR {us}B {note}')
    open(rom_out, 'wb').write(rom_ba)
    print(f'저장: {rom_out}')


if __name__ == '__main__':
    main()
