"""
srwj_decode.py — 슈퍼로봇대전 J (GBA 일본판) 사전 압축 디코더
=============================================================

ROM 내부의 재귀적 사전 압축으로 저장된 대사 텍스트를
일본어(SJIS/CP932)로 복원한다.

[ 사전 구조 ]
  * 헤더 주소: 0xF269D8
  * 헤더 형식: [count u32][0×12바이트 패딩][count × {lim u32, off u32}]
  * 사전 데이터 BASE: 헤더 + 0x10 + count×8
  * 각 세그먼트: (code_lo, code_hi, data_off, el_bytes, kind)
    - sjis   : el=2, 데이터 = 직접 SJIS 2바이트 문자
    - comp   : el=3,4,5,…, 데이터 = 하위 코드열 (재귀 전개)

[ 토크나이저 규칙 ]
  * 바이트 b < 0xC3  → 1바이트 코드  b
  * 바이트 b ≥ 0xC3 → 2바이트 코드  (b<<8)|next
"""

import os
import glob
import struct

# ──────────────────────────────────────────────
#  상수
# ──────────────────────────────────────────────
DICT_HDR   = 0xF269D8   # 사전 헤더 ROM 오프셋
IDX_BASE   = 0xE3097C   # archive1 인덱스 테이블 시작 (0xE3095C + 0x20)
MAX_IDX    = 0x800000   # 인덱스 상한 (ROM 크기 16MB)
CTRL_MARK  = '[{:02X}]'  # 제어코드 표시 형식


# ──────────────────────────────────────────────
#  ROM 로딩
# ──────────────────────────────────────────────
def load_rom(path: str = None) -> bytes:
    """ROM 파일을 로드한다.

    path 가 None 이면 현재 디렉터리의 *.gba 파일을 자동으로 탐색한다.
    여러 개 있으면 알파벳 순 첫 번째를 사용한다.
    """
    if path is None:
        d = os.path.dirname(os.path.abspath(__file__))
        cands = sorted(glob.glob(os.path.join(d, '*.gba')))
        if not cands:
            raise FileNotFoundError(
                '.gba 파일을 이 스크립트와 같은 폴더에 넣어주세요.')
        path = cands[0]
        print(f'[ROM] {os.path.basename(path)} 사용')
    return open(path, 'rb').read()


# ──────────────────────────────────────────────
#  사전 디코더
# ──────────────────────────────────────────────
class Dictionary:
    """슈로대J 재귀 사전 디코더."""

    def __init__(self, rom: bytes):
        self.rom = rom
        self._cache: dict = {}
        self._segs: list = []
        self._hdr = DICT_HDR
        self._parse()

    def _parse(self):
        rom, h = self.rom, self._hdr
        cnt, = struct.unpack_from('<I', rom, h)
        self._base = h + 0x10 + cnt * 8   # 사전 데이터 시작

        # (lim, off) 쌍 읽기
        pairs = []
        o = h + 0x10
        for _ in range(cnt):
            lim, off = struct.unpack_from('<II', rom, o)
            pairs.append((lim, off))
            o += 8

        # 세그먼트 테이블 구성
        # off 값이 0xE0 또는 0x266 인 세그먼트만 'sjis', 나머지는 'comp'
        # el(바이트폭): sjis=2, comp=3,4,5,… 순서대로 증가
        segs = []
        prev = 0
        seen_offs = set()
        comp_n = 3

        for lim, off in pairs:
            if off in seen_offs:
                prev = lim
                continue
            seen_offs.add(off)
            if off in (0xE0, 0x266):
                segs.append((prev, lim, off, 2, 'sjis'))
            else:
                segs.append((prev, lim, off, comp_n, 'comp'))
                comp_n += 1
            prev = lim

        self._segs = segs

    def _find_seg(self, code: int):
        for seg in self._segs:
            if seg[0] <= code < seg[1]:
                return seg
        return None

    def decode(self, code: int, depth: int = 0) -> str:
        """정수 코드 → 일본어 문자열 (재귀)."""
        if depth > 30:
            return '?'
        cached = self._cache.get(code)
        if cached is not None:
            return cached

        seg = self._find_seg(code)
        if seg is None:
            self._cache[code] = '?'
            return '?'

        lo, hi, off, el, kind = seg
        addr = self._hdr + off + (code - lo) * el

        if kind == 'sjis':
            raw = self.rom[addr: addr + 2]
            try:
                result = raw.decode('cp932')
            except Exception:
                result = '□'
            self._cache[code] = result
            return result

        # comp: el 바이트를 읽어 하위 코드열로 재귀 전개
        raw = self.rom[addr: addr + el]
        out = ''
        i = 0
        while i < len(raw):
            b = raw[i]
            if b < 0xC3:
                sub = b
                i += 1
            else:
                if i + 1 < len(raw):
                    sub = (b << 8) | raw[i + 1]
                    i += 2
                else:
                    sub = b
                    i += 1
            out += self.decode(sub, depth + 1)

        self._cache[code] = out
        return out


# ──────────────────────────────────────────────
#  토크나이저
# ──────────────────────────────────────────────
def tokenize(data: bytes) -> list:
    """대사 바이트열을 (int_code, byte_width) 쌍 목록으로 분해.

    Returns:
        list of (code: int, width: int)
          width=1 이면 1바이트 코드, width=2 이면 2바이트 코드.
    """
    tokens = []
    i = 0
    while i < len(data):
        b = data[i]
        if b < 0xC3:
            tokens.append((b, 1))
            i += 1
        else:
            if i + 1 < len(data):
                tokens.append(((b << 8) | data[i + 1], 2))
                i += 2
            else:
                tokens.append((b, 1))
                i += 1
    return tokens


def decode_bytes(data: bytes, dic: Dictionary) -> str:
    """대사 바이트열 전체를 일본어 문자열로 변환."""
    return ''.join(dic.decode(code) for code, _ in tokenize(data))


# ──────────────────────────────────────────────
#  archive1 인덱스 테이블 파싱
# ──────────────────────────────────────────────
def load_archive_index(rom: bytes) -> list:
    """archive1 인덱스 테이블을 읽어 오프셋 목록을 반환.

    반환값: 각 블록의 IDX_BASE 기준 상대 오프셋 목록.
    블록 i 의 ROM 절대주소 = IDX_BASE + index[i]

    인덱스 항목수는 첫 항목으로 확정한다(idx[0] = 항목수 × 4).
    → 블록을 빈 공간으로 재배치해 오프셋이 단조증가하지 않게 되어도
      길이를 올바르게 구할 수 있다.
    """
    first, = struct.unpack_from('<I', rom, IDX_BASE)
    count = first // 4
    if 1 <= count <= 2000 and first % 4 == 0:
        return [struct.unpack_from('<I', rom, IDX_BASE + i * 4)[0]
                for i in range(count)]
    # 폴백: 단조증가 가정으로 탐색
    idx = []
    o = IDX_BASE
    while True:
        v, = struct.unpack_from('<I', rom, o)
        if idx and (v <= idx[-1] or v > MAX_IDX):
            break
        idx.append(v)
        o += 4
        if len(idx) > 2000:
            break
    return idx





def _is_dialogue_block(rom: bytes, addr: int, size: int) -> tuple:
    """(ok: bool, n_dialogues: int) — 이 블록이 대사 블록인지 판별."""
    if size < 16:
        return False, 0
    first, = struct.unpack_from('<I', rom, addr)
    if first < 8 or first % 4 != 0 or first > size:
        return False, 0
    n = first // 4
    if n < 2 or n > 600:
        return False, 0
    ptrs = [struct.unpack_from('<I', rom, addr + k * 4)[0] for k in range(n)]
    if any(ptrs[k + 1] < ptrs[k] for k in range(n - 1)):
        return False, 0
    if ptrs[-1] > size:
        return False, 0
    return True, n - 1   # 마지막 포인터는 종료 마커 → 대사 수 = n-1


def find_all_dialogue_blocks(rom: bytes) -> list:
    """ROM 전체에서 대사 그룹 블록을 찾아 목록 반환.

    Returns:
        list of dict:
          archive_idx  : archive1 내 인덱스 번호
          rom_addr     : ROM 절대주소
          block_size   : 블록 크기 (바이트)
          n_dialogues  : 이 블록의 대사 개수
    """
    idx = load_archive_index(rom)
    blocks = []
    for i in range(len(idx) - 1):
        addr = IDX_BASE + idx[i]
        size = (IDX_BASE + idx[i + 1]) - addr
        ok, n = _is_dialogue_block(rom, addr, size)
        if ok:
            blocks.append(dict(
                archive_idx=i,
                rom_addr=addr,
                block_size=size,
                n_dialogues=n,
            ))
    return blocks
