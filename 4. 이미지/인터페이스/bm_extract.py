# -*- coding: utf-8 -*-
"""전투/UI 이미지 추출 (올바른 인게임 팔레트 적용)

사용법:
  python bm_extract.py <rom.gba> <자산목록.txt 또는 폴더> [출력폴더]
    - 자산목록: 한 줄에 'img_NNNNN_pNNNN' 형식(또는 그런 PNG가 든 폴더의 파일명 사용)
  python bm_extract.py <rom.gba> --list 3941,3942,...  [출력폴더]

핵심: 파일명의 _pXXXX가 항상 실제 인게임 팔레트는 아니다.
pal_override.json(자산번호 → [PLT인덱스, 뱅크])에 교정값이 있으면 그것을 쓰고,
없으면 파일명 PLT의 뱅크0을 사용한다.
출력 PNG는 16색 인덱스(P) 모드, 인덱스0 = 투명(GBA 0번색 관례).

검증된 교정(SRW J): 무기/파츠 라벨 그룹(파일명 p3979)은
실제로 PLT#3899 뱅크2(노란 글자 + 검정 외곽선)를 사용한다.
"""
import sys, os, re, json, struct
from PIL import Image
import scn_title_lib as L

HERE = os.path.dirname(os.path.abspath(__file__))
OVERRIDE = {}
_op = os.path.join(HERE, 'pal_override.json')
if os.path.exists(_op):
    OVERRIDE = {int(k): tuple(v) for k, v in json.load(open(_op, encoding='utf-8')).items() if k.isdigit()}


def plt_bank(rom, plt_i, bank):
    o = L.asset_off(rom, plt_i)
    assert rom[o:o + 3] == b'PLT', f'PLT#{plt_i} 아님'
    n = rom[o + 4]
    base = bank * 16
    cols = []
    for k in range(16):
        v = struct.unpack_from('<H', rom, o + 8 + (base + k) * 2)[0]
        cols.append(((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3))
    return cols


def extract_one(rom, ai, pi):
    img, *_ = L.ecd_decode(rom, ai)
    assert img[:3] == b'IMG'
    tw, th = img[5], img[6]
    tiles = img[8:]
    if ai in OVERRIDE:
        plt_i, bank = OVERRIDE[ai]
    else:
        plt_i, bank = pi, 0
    cols = plt_bank(rom, plt_i, bank)
    im = Image.new('P', (tw * 8, th * 8))
    pal = []
    for c in cols:
        pal += list(c)
    # idx0(투명)은 편집기에서 명확히 보이도록 마젠타로 표시(삽입 시 자동으로 투명 처리됨)
    pal[0:3] = [255, 0, 255]
    im.putpalette(pal + [0] * (768 - len(pal)))
    px = im.load()
    for t in range(tw * th):
        tp = L.tile_get(tiles, t)
        bx, by = (t % tw) * 8, (t // tw) * 8
        for y in range(8):
            for x in range(8):
                px[bx + x, by + y] = tp[y][x]
    im.info['transparency'] = 0  # 인덱스0 투명
    return im, (plt_i, bank)


def parse_targets(arg):
    """arg → [(ai, pi)] 목록"""
    out = []
    if arg.startswith('--list'):
        return None  # 처리는 main에서
    if os.path.isdir(arg):
        for f in sorted(os.listdir(arg)):
            m = re.match(r'img_(\d+)_p(\d+)', f)
            if m:
                out.append((int(m.group(1)), int(m.group(2))))
    else:
        for ln in open(arg, encoding='utf-8'):
            m = re.search(r'img_(\d+)_p(\d+)', ln)
            if m:
                out.append((int(m.group(1)), int(m.group(2))))
    return out


def main():
    rom = open(sys.argv[1], 'rb').read()
    if len(sys.argv) > 2 and sys.argv[2] == '--list':
        ids = [int(x) for x in sys.argv[3].split(',')]
        targets = [(i, None) for i in ids]
        outdir = sys.argv[4] if len(sys.argv) > 4 else '추출'
    else:
        targets = parse_targets(sys.argv[2])
        outdir = sys.argv[3] if len(sys.argv) > 3 else '추출'
    os.makedirs(outdir, exist_ok=True)
    for ai, pi in targets:
        im, (used_plt, bank) = extract_one(rom, ai, pi)
        name = f'img_{ai:05d}_p{(pi if pi else used_plt):04d}.png'
        im.save(os.path.join(outdir, name))
        tag = f'(교정 PLT{used_plt} 뱅크{bank})' if ai in OVERRIDE else ''
        print(f'{name} {im.size} {tag}')
    print('완료:', outdir)


if __name__ == '__main__':
    main()
