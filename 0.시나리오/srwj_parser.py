"""
srwj_parser.py — 슈로대J 대사 블록 파서
=========================================

대사 블록(dialogue group)의 바이너리 구조를 파싱한다.

[ 대사 블록 구조 ]
  +----------------+
  | 포인터 테이블  |  u32 × N  (각 대사의 블록 내 상대 오프셋, 단조 증가)
  +----------------+
  | 대사 #0 데이터 |
  | 대사 #1 데이터 |
  |      …         |
  +----------------+

  * 포인터 테이블 크기(바이트) = ptrs[0]  (첫 포인터값 자체가 테이블 크기)
  * 대사 k 시작주소(ROM) = block_start + ptrs[k]
  * 대사 k 종료주소(ROM) = block_start + ptrs[k+1]  (마지막 대사는 블록 끝까지)

[ 대사(Dialogue) → 턴(Turn) 목록 ]
  하나의 대사(씬)는 여러 말풍선(턴)으로 구성된다.
  각 턴은 [헤더][줄 목록] 으로 이루어진다.

  헤더:
    byte[0] = 화자 ID (character ID)
    byte[1] = 속성 바이트 (attr)
      attr & 0x08 → 보조필드 2바이트 존재
    byte[2~3] = 보조필드 (attr & 0x08 일 때만, 텍스트박스 위치 등)

  줄 목록 (헤더 바로 뒤):
    [길이바이트 1B] [텍스트 '길이바이트 & 0x7F' 바이트]
    길이바이트 ≥ 0x80 → 이 줄이 이 턴의 마지막 줄

  모든 줄 텍스트는 사전 압축 바이트열로 저장된다.
  srwj_decode.decode_bytes() 로 일본어 문자열로 변환할 수 있다.
"""

import struct
from srwj_decode import Dictionary, decode_bytes, IDX_BASE


# ──────────────────────────────────────────────
#  포인터 테이블 파싱
# ──────────────────────────────────────────────
def read_dialogue_pointers(rom: bytes, block_addr: int) -> list:
    """대사 블록의 포인터 테이블을 읽어 상대 오프셋 목록 반환.

    Returns:
        list of int — 블록 시작 기준 상대 오프셋.
        마지막 항목은 종료 마커(= 마지막 대사의 끝 오프셋).
    """
    n_ptrs, = struct.unpack_from('<I', rom, block_addr)
    n_ptrs //= 4
    ptrs = [
        struct.unpack_from('<I', rom, block_addr + i * 4)[0]
        for i in range(n_ptrs)
    ]
    return ptrs


# ──────────────────────────────────────────────
#  턴 파서
# ──────────────────────────────────────────────
def parse_turns(data: bytes) -> tuple:
    """대사 데이터를 턴 목록으로 파싱.

    Args:
        data: 하나의 대사 바이트열

    Returns:
        (turns, success)
          turns  : list of dict
          success: True 이면 끝까지 정상 파싱됨

    턴 dict 구조:
        cid   : int   — 화자 ID
        attr  : int   — 속성 바이트
        aux   : bytes | None — 보조필드 (attr & 0x08 일 때 2바이트, 아니면 None)
        lines : list of bytes — 줄별 사전 압축 바이트열
    """
    turns = []
    p = 0
    ok = True

    while p < len(data):
        if p + 2 > len(data):
            ok = (p == len(data))
            break

        cid  = data[p]
        attr = data[p + 1]
        hp   = p + 2
        aux  = None

        if attr & 0x08:
            if hp + 2 > len(data):
                ok = False
                break
            aux = bytes(data[hp: hp + 2])
            hp += 2

        lines = []
        q = hp
        closed = False

        while q < len(data):
            if q >= len(data):
                break
            lb = data[q]
            q += 1
            ln = lb & 0x7F

            if q + ln > len(data):
                ok = False
                break

            lines.append(bytes(data[q: q + ln]))
            q += ln

            if lb & 0x80:   # 마지막 줄 플래그
                closed = True
                break

        if not closed:
            ok = False

        turns.append(dict(cid=cid, attr=attr, aux=aux, lines=lines))
        p = q

        if not ok:
            break

    return turns, (ok and p == len(data))


# ──────────────────────────────────────────────
#  대사 블록 전체 파싱
# ──────────────────────────────────────────────
def parse_dialogue_block(rom: bytes, block_addr: int, block_size: int,
                          dic: Dictionary) -> dict:
    """대사 블록 하나 전체를 파싱하여 구조화된 dict 반환.

    Returns:
        dict:
          block_addr   : int   — ROM 절대주소
          block_size   : int   — 블록 크기
          n_dialogues  : int   — 대사 개수
          dialogues    : list of dict
            각 대사 dict:
              idx        : int  — 이 블록 내 대사 인덱스 (0-based)
              rom_start  : int  — 대사 데이터 ROM 절대주소
              rom_end    : int  — 대사 데이터 ROM 종료주소 (exclusive)
              data_size  : int  — 바이트 크기
              parse_ok   : bool — 파싱 성공 여부
              turns      : list of dict (parse_turns 반환)
              text       : str  — 모든 줄을 합친 일본어 텍스트
    """
    ptrs = read_dialogue_pointers(rom, block_addr)
    n = len(ptrs) - 1   # 마지막은 종료 마커

    dialogues = []
    for d in range(n):
        start = block_addr + ptrs[d]
        end   = block_addr + ptrs[d + 1]
        data  = rom[start: end]

        if not data:
            dialogues.append(dict(
                idx=d, rom_start=start, rom_end=end, data_size=0,
                parse_ok=True, turns=[], text=''))
            continue

        turns, ok = parse_turns(data)

        # 전체 텍스트 합성 (줄 사이 '\n', 턴 사이 '\n\n')
        turn_texts = []
        for t in turns:
            line_texts = [decode_bytes(ln, dic) for ln in t['lines']]
            turn_texts.append('\n'.join(line_texts))
        full_text = '\n\n'.join(turn_texts)

        # 각 턴에 decoded_text 필드 추가
        for t in turns:
            t['decoded'] = '\n'.join(decode_bytes(ln, dic) for ln in t['lines'])

        dialogues.append(dict(
            idx=d,
            rom_start=start,
            rom_end=end,
            data_size=len(data),
            parse_ok=ok,
            turns=turns,
            text=full_text,
        ))

    return dict(
        block_addr=block_addr,
        block_size=block_size,
        n_dialogues=n,
        dialogues=dialogues,
    )
