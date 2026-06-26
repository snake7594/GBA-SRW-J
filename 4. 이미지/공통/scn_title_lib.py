# -*- coding: utf-8 -*-
"""SRW J 시나리오 제목 공용 라이브러리
ECD(LZSS) 코덱 + 아카이브 입출력 + IMG/SCR 해석

[검증된 포맷 사양]
- 아카이브 인덱스: 0x1D6DE4, 4바이트 LE 상대 오프셋 x 15447
- ECD 헤더 16바이트: 'ECD\\x01' + prefix길이(BE4) + 압축크기(BE4) + 원본크기(BE4)
  * prefix(보통 8바이트, IMG/SCR/PLT 헤더)는 비압축 원문으로 저장되며 LZSS 윈도에 넣지 않음
- LZSS: 윈도 1024(0으로 초기화), 쓰기 시작 위치 0x3BE(=1024-66)
  플래그 바이트 LSB부터, 비트1=리터럴 1바이트, 비트0=매치 2바이트
  매치: pos = b1 | ((b2>>6)<<8)  (윈도 절대 위치), len = (b2&0x3F)+3 (3~66)
- IMG prefix: 'IMG\\0' 0 tw th 0  (tw,th = 타일 단위 크기, 4bpp 8x8 타일, 행우선)
- SCR prefix: 'SCR\\0' 0 w h 0  (셀 2바이트 LE: bit0-9 타일번호, 10 h플립, 11 v플립, 12-15 뱅크)
- 제목 화면: 화 n → IMG 3462+n, SCR 3531+n (n=0..67)
  게임은 스트립을 VRAM(스트라이드 32타일/행)에 적재:
  저장타일 s = (VRAM타일//32)*tw + (VRAM타일%32)
  SCR은 화면행 7,8(1행=第N話), 11,12(2행=부제), (13,14 = 3행, ep59)에 배치
- 화 0~32: PLT#3460 계열, 화 33~67: PLT#3530 계열 (표시용 색상; 픽셀값=팔레트 인덱스)
"""
import struct

BASE = 0x1D6DE4
N_ASSETS = 15447
EP_IMG0 = 3462
EP_SCR0 = 3531
N_EP = 68
CANVAS_ROW0 = 7          # 캔버스 y0 = 화면 타일행 7
CANVAS_ROWS = 8          # 행 7..14 (240x64 캔버스)
ROW_PAIRS = [(7, 8), (9, 10), (11, 12), (13, 14)]  # 텍스트 줄 후보(2행 단위)


def asset_off(rom, i):
    return BASE + struct.unpack_from('<I', rom, BASE + i * 4)[0]


def asset_slot(rom, i):
    """이 자산이 차지할 수 있는 최대 바이트.
    재배치된 자산이 섞여 있으면 인덱스 순서 != 물리 순서이므로,
    '물리적으로 바로 다음에 있는 자산'까지의 거리로 계산한다."""
    o = asset_off(rom, i)
    nxt = None
    for k in range(N_ASSETS):
        ok = BASE + struct.unpack_from('<I', rom, BASE + k * 4)[0]
        if ok > o and (nxt is None or ok < nxt):
            nxt = ok
    if nxt is None:
        nxt = len(rom)
    return nxt - o


def ecd_decode(rom, i):
    """자산 i 디코드 → (data, off, prefix_len, comp, dec)"""
    o = asset_off(rom, i)
    if rom[o:o + 4] != b'ECD\x01':
        raise ValueError(f'asset {i}: ECD 아님 @{o:#x}')
    plen = struct.unpack_from('>I', rom, o + 4)[0]
    comp = struct.unpack_from('>I', rom, o + 8)[0]
    dec = struct.unpack_from('>I', rom, o + 12)[0]
    out = bytearray(rom[o + 16:o + 16 + plen])
    win = bytearray(1024)
    wp = 0x3BE
    flag = 0
    nb = 0
    p = o + 16 + plen
    while len(out) < dec:
        if nb == 0:
            flag = rom[p]; p += 1; nb = 8
        bit = flag & 1; flag >>= 1; nb -= 1
        if bit:
            b = rom[p]; p += 1
            out.append(b); win[wp] = b; wp = (wp + 1) & 1023
        else:
            b1, b2 = rom[p], rom[p + 1]; p += 2
            pos = b1 | ((b2 >> 6) << 8)
            ln = (b2 & 0x3F) + 3
            src = pos
            for _ in range(ln):
                b = win[src]; src = (src + 1) & 1023
                out.append(b); win[wp] = b; wp = (wp + 1) & 1023
                if len(out) >= dec:
                    break
    return bytes(out), o, plen, comp, dec


def ecd_encode(data, plen):
    """data(prefix 포함) → ECD 페이로드(prefix + 비트스트림). 헤더 미포함.
    최적 파싱(DP). 매치 = 거리 D(1..1024) 후방 복사, 시작 전 영역은 가상 0."""
    prefix = bytes(data[:plen])
    body = bytes(data[plen:])
    n = len(body)
    ext = b'\x00' * 1024 + body  # 가상 0-프리픽스

    # 위치별 최장 매치 (길이, 거리)
    best = [(0, 0)] * n
    occ = {}  # 바이트 → ext 인덱스 목록(최근 1024개만 유효)
    for j in range(1024):
        occ.setdefault(0, []).append(j)
    for i in range(n):
        e = 1024 + i
        maxl = min(66, n - i)
        bl, bd = 0, 0
        if maxl >= 3:
            cand = occ.get(body[i], ())
            for j in reversed(cand):
                if j < e - 1024:
                    break
                d = e - j
                l = 0
                while l < maxl and ext[e + l - d] == ext[e + l]:
                    l += 1
                if l > bl:
                    bl, bd = l, d
                    if l == maxl:
                        break
        best[i] = (bl, bd)
        occ.setdefault(body[i], []).append(e)

    # DP (1/8바이트 단위 비용: 리터럴 9, 매치 17)
    INF = 1 << 30
    cost = [0] * (n + 1)
    choice = [0] * n  # 0=리터럴, l>=3 = 매치 길이
    for i in range(n - 1, -1, -1):
        c = 9 + cost[i + 1]
        ch = 0
        bl, bd = best[i]
        for l in range(3, bl + 1):
            cc = 17 + cost[i + l]
            if cc < c:
                c = cc; ch = l
        cost[i] = c
        choice[i] = ch

    # 방출
    outb = bytearray()
    flags = 0; nf = 0; fpos = -1
    def put(bit):
        nonlocal flags, nf, fpos
        if nf == 0:
            fpos = len(outb); outb.append(0); flags = 0
        flags |= bit << nf
        nf += 1
        outb[fpos] = flags
        if nf == 8:
            nf = 0
    i = 0
    while i < n:
        l = choice[i]
        if l >= 3:
            d = best[i][1]
            wp = (0x3BE + i) & 1023
            pos = (wp - d) & 1023
            put(0)
            outb.append(pos & 0xFF)
            outb.append(((pos >> 8) << 6) | (l - 3))
            i += l
        else:
            put(1)
            outb.append(body[i])
            i += 1
    return prefix + bytes(outb)


RELOC_BASE = 0x1800000  # 슬롯 초과 자산 재배치 영역(ROM 끝 여유 공간)


def _reloc_cursor(rom_ba):
    """재배치 영역에서 다음 빈 위치 탐색.
    ECD를 순차로 건너뛰는 방식은 자산 사이에 비-ECD 구간이 있으면 거기서 멈춰
    기존(이미 재배치된) 자산을 덮어쓸 수 있다. 그래서 인덱스 테이블 전체를 스캔해
    RELOC_BASE 이상에 있는 모든 자산의 '실제 끝점' 중 최대값 뒤에 배치한다.
    이렇게 하면 이전 세션에서 재배치된 자산이 섞여 있어도 절대 덮어쓰지 않는다."""
    cursor = RELOC_BASE
    for k in range(N_ASSETS):
        ok = BASE + struct.unpack_from('<I', rom_ba, BASE + k * 4)[0]
        if ok < RELOC_BASE or ok + 16 > len(rom_ba):
            continue
        if rom_ba[ok:ok + 4] != b'ECD\x01':
            continue
        comp = struct.unpack_from('>I', rom_ba, ok + 8)[0]
        end = ok + ((16 + comp + 3) & ~3)
        if end > cursor:
            cursor = end
    return cursor


def ecd_write(rom_ba, i, data, plen, allow_reloc=True):
    """자산 i 자리에 data를 ECD로 압축해 기록.
    슬롯 초과 시 allow_reloc=True면 RELOC_BASE 영역에 기록하고 인덱스를 갱신."""
    o = asset_off(rom_ba, i)
    slot = asset_slot(rom_ba, i)
    payload = ecd_encode(data, plen)
    total = 16 + len(payload)
    relocated = False
    if total > slot:
        if not allow_reloc:
            raise ValueError(f'asset {i}: 압축 {total}B > 슬롯 {slot}B')
        o = _reloc_cursor(rom_ba)
        if o + total > len(rom_ba):
            raise ValueError(f'asset {i}: 재배치 공간 부족')
        struct.pack_into('<I', rom_ba, BASE + i * 4, o - BASE)
        relocated = True
    struct.pack_into('>I', rom_ba, o, 0x45434401)  # 'ECD\x01'
    struct.pack_into('>I', rom_ba, o + 4, plen)
    struct.pack_into('>I', rom_ba, o + 8, len(payload))
    struct.pack_into('>I', rom_ba, o + 12, len(data))
    rom_ba[o + 16:o + 16 + len(payload)] = payload
    if not relocated and slot - total <= 65536:
        for k in range(o + 16 + len(payload), o + slot):
            rom_ba[k] = 0
    # 라운드트립 검증
    chk, *_ = ecd_decode(bytes(rom_ba), i)
    if chk != bytes(data):
        raise RuntimeError(f'asset {i}: 라운드트립 검증 실패')
    return total, relocated


# ---------- IMG / SCR ----------

def img_parse(data):
    """IMG 자산 → (tw, th, tiles[bytes])"""
    assert data[:3] == b'IMG'
    tw, th = data[5], data[6]
    return tw, th, data[8:]


def img_build(tw, th, tiles):
    return bytes([0x49, 0x4D, 0x47, 0, 0, tw, th, 0]) + bytes(tiles)


def scr_parse(data):
    """SCR 자산 → (w, h, ents[list of int])"""
    assert data[:3] == b'SCR'
    w, h = data[5], data[6]
    ents = list(struct.unpack_from(f'<{w*h}H', data, 8))
    return w, h, ents


def scr_build(w, h, ents):
    return bytes([0x53, 0x43, 0x52, 0, 0, w, h, 0]) + struct.pack(f'<{w*h}H', *ents)


def tile_get(tiles, t):
    """타일 t → 8x8 인덱스 2차원 리스트"""
    p = [[0] * 8 for _ in range(8)]
    b = t * 32
    for r in range(8):
        for c in range(4):
            v = tiles[b + r * 4 + c]
            p[r][c * 2] = v & 0xF
            p[r][c * 2 + 1] = (v >> 4) & 0xF
    return p


def tile_put(tiles, t, p):
    b = t * 32
    for r in range(8):
        for c in range(4):
            tiles[b + r * 4 + c] = (p[r][c * 2] & 0xF) | ((p[r][c * 2 + 1] & 0xF) << 4)


def vram_to_storage(t, tw):
    """VRAM 타일번호 → 저장 타일 인덱스"""
    return (t // 32) * tw + (t % 32)


def storage_to_vram(s, tw):
    return (s // tw) * 32 + (s % tw)
