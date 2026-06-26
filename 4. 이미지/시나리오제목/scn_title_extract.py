# -*- coding: utf-8 -*-
"""시나리오 제목 추출: ROM → 편집용 PNG (게임 화면 그대로의 배치)

사용법:
  python scn_title_extract.py <rom.gba> [출력폴더] [--sheet]

출력: e00_img3462.png ... e67_img3529.png  (RGBA 240x64)
  - 캔버스 y0 = 화면 타일행 7 (즉 화면 y56). 행 7,8 = 1행(第N話), 11,12 = 2행, 13,14 = 3행(59화만)
  - 투명 = 색 0. 잉크 = 회색 단계. 제목 팔레트는 반전형이라 인덱스 v -> 회색 (16-v)*17
    (인덱스1 = 흰 본문 -> 255, 인덱스15 = 검정 외곽선 -> 17). 편집용 PNG는 게임과 같은 흰 본문/검정 외곽선
  - 편집 후 scn_title_insert.py 로 재삽입 (잉크 색은 회색 17단계에 가장 가까운 값으로 환원됨)
"""
import sys, os
from PIL import Image
import scn_title_lib as L


def extract_ep(rom, n):
    img, *_ = L.ecd_decode(rom, L.EP_IMG0 + n)
    scr, *_ = L.ecd_decode(rom, L.EP_SCR0 + n)
    tw, th, tiles = L.img_parse(img)
    w, h, ents = L.scr_parse(scr)
    canvas = Image.new('RGBA', (w * 8, L.CANVAS_ROWS * 8), (0, 0, 0, 0))
    px = canvas.load()
    for r in range(h):
        cy = r - L.CANVAS_ROW0
        if not (0 <= cy < L.CANVAS_ROWS):
            continue
        for c in range(w):
            e = ents[r * w + c]
            t = e & 0x3FF
            if t == 0:
                continue
            s = L.vram_to_storage(t, tw)
            tp = L.tile_get(tiles, s)
            hf, vf = (e >> 10) & 1, (e >> 11) & 1
            for yy in range(8):
                for xx in range(8):
                    sy = 7 - yy if vf else yy
                    sx = 7 - xx if hf else xx
                    v = tp[sy][sx]
                    if v:
                        # 반전 팔레트: 인덱스1=흰 본문(→255), 인덱스15=검정 외곽선(→17)
                        g = (16 - v) * 17
                        px[c * 8 + xx, cy * 8 + yy] = (g, g, g, 255)
    return canvas, (tw, th, len(tiles) // 32)


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else 'rom.gba'
    outdir = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else '시나리오제목_편집용'
    os.makedirs(outdir, exist_ok=True)
    rom = open(rom_path, 'rb').read()
    infos = []
    for n in range(L.N_EP):
        canvas, info = extract_ep(rom, n)
        fn = os.path.join(outdir, f'e{n:02d}_img{L.EP_IMG0 + n:05d}.png')
        canvas.save(fn)
        infos.append((n, canvas, info))
        print(f'{fn}  (타일 {info[0]}x{info[1]} = {info[2]}개, 잉크 셀 한도 {info[2] - 1})')
    if '--sheet' in sys.argv:
        # 점검용 시트 (어두운 배경 합성)
        W, H = 240 * 2, ((L.N_EP + 1) // 2) * (64 + 14)
        sheet = Image.new('RGB', (W, H), (30, 30, 30))
        from PIL import ImageDraw
        dr = ImageDraw.Draw(sheet)
        for n, canvas, info in infos:
            x = (n % 2) * 240
            y = (n // 2) * (64 + 14)
            dr.text((x + 2, y), f'e{n:02d} img{L.EP_IMG0 + n} {info[0]}x{info[1]}', fill=(255, 255, 0))
            bg = Image.new('RGBA', canvas.size, (70, 10, 10, 255))
            bg.alpha_composite(canvas)
            sheet.paste(bg.convert('RGB'), (x, y + 12))
        sheet.save(os.path.join(outdir, '_점검시트.png'))
        print('점검시트 저장')


if __name__ == '__main__':
    main()
