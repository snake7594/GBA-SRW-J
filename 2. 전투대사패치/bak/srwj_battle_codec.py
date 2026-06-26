# -*- coding: utf-8 -*-
"""
srwj_battle_codec.py — 슈퍼로봇대전 J 전투 텍스트 블록 코덱

검증된 사실(컨테이너 테스트):
- 코드표 0xFB18B8(0x00~0x78), 0x00=！, 0x01=・, 0x7b=개행
- 0x78/79/7a/7c = 대사 구분자(SEP), 0x7d/7e/7f/80 = 인라인 코드(이름/변수)
- 1바이트 0x78은 구분자이므로 한자 大는 반드시 2바이트(0x91e5)로 인코딩(INV1에서 0x78 제외)
- 각 유닛 블록(194~370)은 10개 (offset,count) 쌍 = 40바이트 고정 헤더.
  offset0=0x28, 카테고리 i 데이터 = block[off_i:off_{i+1}]
- 왕복(parse→rebuild) 178/178, 재구성(헤더 재계산 포함) 177/177 바이트 동일 검증
- 한글은 SJIS에 없어 2바이트 가이지(미사용 선두 0xF0~0xFC)로 인코딩
"""
import struct, re

SEP = {0x78, 0x79, 0x7a, 0x7c}
INLINE = {0x7d, 0x7e, 0x7f, 0x80}
MARK = re.compile(r'\[([0-9a-f]{2})\]')

class BattleCodec:
    def __init__(self, rom, tbl=None, idx_base=0xE3097C):
        self.IDX_BASE = idx_base
        # 코드표는 블록 371(CODETABLE_IDX). 재배치되어도 인덱스에서 실제 위치를 읽는다.
        if tbl is None:
            tbl = idx_base + struct.unpack_from('<I', rom, idx_base + 371*4)[0]
        self.tbl = tbl
        self.T = {}
        for c in range(0x79):
            w = rom[tbl + c*2: tbl + c*2 + 2]
            try: self.T[c] = w.decode('shift_jis')
            except: self.T[c] = None
        # 역코드표: 구분자(0x78)·인라인코드는 제외 → 大 등은 2바이트로
        self.INV1 = {ch: c for c, ch in self.T.items()
                     if ch and c not in SEP and c not in INLINE}
        self.gaiji = {}       # char -> (hi, lo)
        self.gaiji_rev = {}   # (hi, lo) -> char

    def blkoff(self, rom, k):
        return self.IDX_BASE + struct.unpack_from('<I', rom, self.IDX_BASE + k*4)[0]

    def set_gaiji(self, genmap):
        """genmap: {char: [hi, lo]}"""
        self.gaiji = {ch: tuple(v) for ch, v in genmap.items()}
        self.gaiji_rev = {tuple(v): ch for ch, v in genmap.items()}

    # ---- 디코드: 블록 바이트 → 토큰열 [('t',텍스트) | ('x',구분자바이트)] ----
    def parse(self, b):
        toks = []; cur = []
        def flush():
            if cur: toks.append(('t', ''.join(cur))); cur.clear()
        i = 0; n = len(b)
        while i < n:
            x = b[i]
            if 0x81 <= x <= 0x9f or 0xe0 <= x <= 0xfc:
                if i+1 < n:
                    pair = b[i:i+2]
                    try:
                        cur.append(pair.decode('shift_jis')); i += 2; continue
                    except Exception:
                        if (x, b[i+1]) in self.gaiji_rev:      # 한글 가이지
                            cur.append(self.gaiji_rev[(x, b[i+1])]); i += 2; continue
                cur.append(f'[{x:02x}]'); i += 1
            elif x == 0x7b: cur.append('\n'); i += 1
            elif x in SEP: flush(); toks.append(('x', x)); i += 1
            elif 0xa1 <= x <= 0xdf:
                try: cur.append(bytes([x]).decode('shift_jis')); i += 1
                except Exception: cur.append(f'[{x:02x}]'); i += 1
            elif x < 0x79 and self.T[x] is not None:
                cur.append(self.T[x]); i += 1
            else:
                cur.append(f'[{x:02x}]'); i += 1   # 0x7d/7e/7f/80 등 인라인코드
        flush(); return toks

    # ---- 인코드: 텍스트 → 바이트 ----
    def enc_text(self, s, assign=False):
        out = bytearray(); i = 0
        while i < len(s):
            m = MARK.match(s, i)
            if m:
                out.append(int(m.group(1), 16)); i = m.end(); continue
            ch = s[i]; i += 1
            if ch == '\n': out.append(0x7b)
            elif ch in self.INV1: out.append(self.INV1[ch])
            elif ch in self.gaiji: out += bytes(self.gaiji[ch])
            else:
                try:
                    out += ch.encode('shift_jis')       # 일본어
                except Exception:
                    if assign:                          # 한글 등 신규 가이지 배정
                        code = self._alloc_gaiji(ch); out += bytes(code)
                    else:
                        raise ValueError(f"인코딩 불가(가이지 미배정): {ch!r}")
        return bytes(out)

    def _alloc_gaiji(self, ch):
        used = set(self.gaiji.values())
        for hi in range(0xF0, 0xFD):
            for lo in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
                if (hi, lo) not in used:
                    self.gaiji[ch] = (hi, lo); self.gaiji_rev[(hi, lo)] = ch
                    return (hi, lo)
        raise RuntimeError("가이지 슬롯 소진")

    def rebuild(self, toks, assign=False):
        out = bytearray()
        for t in toks:
            out += self.enc_text(t[1], assign) if t[0] == 't' else bytes([t[1]])
        return bytes(out)

    # ---- 블록 재구성: 헤더 파싱 → 카테고리별 재인코딩 → 오프셋 재계산 ----
    def reconstruct(self, block, translate=None, assign=False):
        """translate: 텍스트토큰 -> 새 텍스트(또는 None=유지) 콜러블"""
        u16 = lambda o: block[o] | (block[o+1] << 8)
        pairs = [(u16(i*4), u16(i*4+2)) for i in range(10)]
        offs = [p[0] for p in pairs]; cnt = [p[1] for p in pairs]
        bounds = offs + [len(block)]
        cats = []
        for i in range(10):
            toks = self.parse(block[bounds[i]:bounds[i+1]])
            if translate:
                nt = []
                for t in toks:
                    if t[0] == 't':
                        r = translate(t[1])
                        nt.append(('t', r if r is not None else t[1]))
                    else:
                        nt.append(t)
                toks = nt
            cats.append(self.rebuild(toks, assign))
        new_offs = [0x28]
        for i in range(9): new_offs.append(new_offs[i] + len(cats[i]))
        hdr = b''.join(struct.pack('<HH', new_offs[i], cnt[i]) for i in range(10))
        return hdr + b''.join(cats)


def self_test(rom_path='jp.gba'):
    rom = open(rom_path, 'rb').read()
    cx = BattleCodec(rom)
    rt = rc = tot = 0
    for k in range(193, 371):
        b = rom[cx.blkoff(rom, k):cx.blkoff(rom, k+1)]; tot += 1
        if cx.rebuild(cx.parse(b)) == b: rt += 1
        if k >= 194 and cx.reconstruct(b) == b: rc += 1
    print(f"[self_test] 왕복 {rt}/{tot}, 재구성 {rc}/177")
    assert rt == tot and rc == 177, "코덱 항등 검증 실패!"
    print("[self_test] OK — 코덱 무손상 확인")

if __name__ == '__main__':
    self_test()
