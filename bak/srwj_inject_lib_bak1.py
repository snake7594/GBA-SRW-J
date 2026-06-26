# -*- coding: utf-8 -*-
"""
srwj_inject_lib.py — 한글 대사 삽입 공통 함수

patch_all.py 가 사용하는 블록 재구성 · 희생슬롯 순위 계산 등.
"""

from collections import Counter

import srwj_decode as D
import srwj_parser as P

SEG1_LO, SEG1_HI = 0xC300, 0xCA3B


# ──────────────────────────────────────────────────────────
#  턴 재구성
# ──────────────────────────────────────────────────────────
def rebuild_turn_original(turn) -> bytes:
    """파싱된 턴을 원본(일본어) 바이트열로 복원."""
    out = bytearray([turn['cid'], turn['attr']])
    if turn['aux'] is not None:
        out += turn['aux']
    n = len(turn['lines'])
    for i, line in enumerate(turn['lines']):
        lb = (len(line) & 0x7F) | (0x80 if i == n - 1 else 0)
        out.append(lb)
        out += line
    return bytes(out)


def rebuild_turn_korean(turn, kr_lines, codec) -> bytes:
    """턴 헤더(화자/속성/보조) + 한국어 줄들로 새 턴 바이트열 생성."""
    out = bytearray([turn['cid'], turn['attr']])
    if turn['aux'] is not None:
        out += turn['aux']
    encoded = [codec.encode_line(s) for s in kr_lines]
    n = len(encoded)
    for i, enc in enumerate(encoded):
        if len(enc) > 0x7F:
            raise ValueError(f'줄 길이 {len(enc)} > 127 바이트')
        lb = (len(enc) & 0x7F) | (0x80 if i == n - 1 else 0)
        out.append(lb)
        out += enc
    return bytes(out)


# ──────────────────────────────────────────────────────────
#  희생슬롯 우선순위 (동적 계산)
# ──────────────────────────────────────────────────────────
def seg1_codes_of_block(rom, dic, meta):
    """블록 하나가 쓰는 seg1 2바이트 코드 집합."""
    bi = P.parse_dialogue_block(rom, meta['rom_addr'], meta['block_size'], dic)
    used = set()
    for dlg in bi['dialogues']:
        for t in dlg['turns']:
            for ln in t['lines']:
                for code, w in D.tokenize(ln):
                    if w == 2 and SEG1_LO <= code < SEG1_HI:
                        used.add(code)
    return used


def compute_victim_rank(rom, dic, blocks, translated_archive):
    """seg1 코드를 '희생시켜도 덜 위험한 순서'로 정렬해 반환.

    번역 대상 블록은 원문이 폐기되므로 사용량 집계에서 제외한다.
    → 번역하는 챕터가 많아질수록 자유롭게 쓸 수 있는 슬롯이 늘어난다.

    Args:
        blocks             : find_all_dialogue_blocks 결과(순서대로)
        translated_archive : 이번에 번역하는 블록의 archive 인덱스 집합

    Returns: (seg1 코드 리스트(앞쪽일수록 안전), 코드별 사용횟수)
    """
    code_use = Counter()
    for meta in blocks:
        if meta['archive_idx'] in translated_archive:
            continue                       # 번역될 블록 → 집계 제외
        for c in seg1_codes_of_block(rom, dic, meta):
            code_use[c] += 1
    seg1 = list(range(SEG1_LO, SEG1_HI))
    seg1.sort(key=lambda c: (code_use.get(c, 0), c))
    return seg1, code_use


# ──────────────────────────────────────────────────────────
#  한국어 블록 빌드
# ──────────────────────────────────────────────────────────
def build_korean_block(rom, dic, meta, kr_by_turn, codec, reserve,
                        fit_func, placeholder=None):
    """블록 하나를 한국어로 재구성한 바이트열 생성.

    Args:
        meta        : 블록 메타(find_all_dialogue_blocks 항목)
        kr_by_turn  : 턴 순번 → 한국어 텍스트 (없으면 미번역)
        codec       : HangulCodec (plan 완료 상태)
        reserve     : 첫 줄 "화자「" 폭
        fit_func    : srwj_wrap.fit_turn_lines
        placeholder : 미번역 턴에 넣을 표시 문구. None 이면 원본 일본어 유지.

    Returns:
        (new_block_bytes, stats)
          stats: dict(n_dialogues, n_turns, kr_turns, jp_turns,
                      ph_turns, warn_minor, warn_major)
    """
    info = P.parse_dialogue_block(rom, meta['rom_addr'],
                                  meta['block_size'], dic)
    flat = []
    for dlg in info['dialogues']:
        for turn in dlg['turns']:
            flat.append(turn)

    new_turns = []
    kr_cnt = jp_cnt = ph_cnt = 0
    warn_minor = warn_major = 0

    for i, turn in enumerate(flat):
        kr = kr_by_turn.get(i)
        jp_lines = len(turn['lines'])

        # ── 번역이 없는 턴 ──
        if not kr or not str(kr).strip():
            if placeholder is not None:
                try:
                    new_turns.append(
                        rebuild_turn_korean(turn, [placeholder], codec))
                    ph_cnt += 1
                except ValueError:
                    new_turns.append(rebuild_turn_original(turn))
                    jp_cnt += 1
            else:
                new_turns.append(rebuild_turn_original(turn))
                jp_cnt += 1
            continue

        # ── 번역이 있는 턴 ──
        lines, warns = fit_func(str(kr), jp_lines, reserve)
        try:
            new_turns.append(rebuild_turn_korean(turn, lines, codec))
        except ValueError:
            new_turns.append(rebuild_turn_original(turn))
            jp_cnt += 1
            continue
        kr_cnt += 1
        if warns:
            extra = len(lines) - jp_lines
            if extra >= 2:
                warn_major += 1
            elif extra >= 1:
                warn_minor += 1

    # 대사별로 턴 합치기
    dlg_bytes = []
    ti = 0
    for dlg in info['dialogues']:
        buf = bytearray()
        for _ in dlg['turns']:
            buf += new_turns[ti]
            ti += 1
        dlg_bytes.append(bytes(buf))

    n_ptr = len(info['dialogues']) + 1
    ptrs = [n_ptr * 4]
    for db in dlg_bytes:
        ptrs.append(ptrs[-1] + len(db))

    block = bytearray()
    for p in ptrs:
        block += p.to_bytes(4, 'little')
    for db in dlg_bytes:
        block += db

    stats = dict(n_dialogues=len(info['dialogues']), n_turns=len(flat),
                 kr_turns=kr_cnt, jp_turns=jp_cnt, ph_turns=ph_cnt,
                 warn_minor=warn_minor, warn_major=warn_major)
    return bytes(block), stats


# ──────────────────────────────────────────────────────────
#  ROM 용량 확장
# ──────────────────────────────────────────────────────────
GBA_MAX = 32 * 1024 * 1024          # GBA ROM 최대 32MB


def ensure_rom_capacity(rom: bytearray, end_addr: int):
    """end_addr 까지 쓸 수 있도록 ROM 크기를 확장(필요 시).

    GBA 카트리지 주소공간(최대 32MB)에 맞춰 2의 거듭제곱으로 키운다.
    Returns: 최종 ROM 크기. 32MB 초과 시 예외.
    """
    if end_addr <= len(rom):
        return len(rom)
    newsize = 1
    while newsize < end_addr:
        newsize <<= 1
    if newsize > GBA_MAX:
        raise ValueError(
            f'필요 크기 {end_addr:,} 가 GBA 최대 32MB 를 초과합니다.')
    rom.extend(b'\xFF' * (newsize - len(rom)))
    return newsize


# ──────────────────────────────────────────────────────────
#  사전 확장 (seg1 코드 슬롯 늘리기)
# ──────────────────────────────────────────────────────────
#  사전 헤더 0xF269D8 구조: [count u32][12 pad][count×(lim u32, off u32)]
#
#  실제 쌍 배열(중요):
#    pair[0] = seg0       (lim 0xC300, off 0xE0)
#    pair[1] = seg1       (lim 0xCA3B, off 0x266)
#    pair[2] = seg1 중복  (lim 0xCA3B, off 0x266)  ← pair[1] 과 동일
#    pair[3] = seg2(압축) (lim 0xE2EB, off 0x10DC, el=3, 6320엔트리)
#
#  디코더는 pair[2] 를 'off 중복'으로 건너뛴다. 따라서 seg1 을 확장할 때는
#  pair[1] 과 pair[2] 의 lim 을 '둘 다' 같은 새 값으로 써야 한다
#  (그래야 pair[2] 가 계속 pair[1] 의 정상적인 중복으로 남는다).
HDR = D.DICT_HDR
SEG1_PAIR     = HDR + 0x10 + 1 * 8   # pair[1]  seg1
SEG1_PAIR_DUP = HDR + 0x10 + 2 * 8   # pair[2]  seg1 중복(동기화 필요)
SEG2_PAIR     = HDR + 0x10 + 3 * 8   # pair[3]  진짜 seg2(압축)
SEG2_OFF      = 0x10DC               # seg2 압축 테이블의 헤더기준 오프셋
SEG2_EL       = 3
SEG2_COUNT    = 6320                 # 원본 seg2 엔트리 수


def expand_dictionary(rom: bytearray, n_extra: int, free_addr: int):
    """seg1 의 코드 슬롯을 n_extra 개 늘린다.

    방법:
      * seg1.lim(= pair[1], pair[2] 둘 다)을 n_extra 만큼 키워
        코드 0xCA3B~ 를 seg1(직접 SJIS)에 편입.
      * 그 코드들이 쓰던 seg2(압축) 테이블의 앞부분을 잘라내고,
        남는 부분을 ROM 빈 공간으로 이전(pair[3].off 수정).
      * seg1.off(0x266) 와 seg2.lim, 다른 세그먼트는 그대로 → 호환 안정.

    Returns: seg2 테이블 이전 후 다음 빈 주소.

    주의: 코드 0xCA3B~ 가 압축→직접 으로 바뀌므로, 아직 번역하지 않은
          챕터에서 그 코드를 쓰던 일부 글자가 다르게 보일 수 있다.
          (전체 챕터 번역 시 자연 해소)
    """
    if n_extra <= 0:
        return free_addr
    if n_extra > SEG2_COUNT:
        raise ValueError(f'사전 확장 한계 초과 (요청 {n_extra} > {SEG2_COUNT})')

    import struct
    # 1) seg2 압축 테이블에서 '남는 부분'만 빈 공간으로 복사
    #    (앞 n_extra 엔트리는 seg1 으로 넘어가므로 버림)
    seg2_tbl_start = HDR + SEG2_OFF
    seg2_tbl_end   = seg2_tbl_start + SEG2_COUNT * SEG2_EL
    new_seg2_tbl = bytes(rom[seg2_tbl_start + n_extra * SEG2_EL: seg2_tbl_end])

    free_addr = (free_addr + 3) & ~3
    end = free_addr + len(new_seg2_tbl)
    ensure_rom_capacity(rom, end)
    rom[free_addr:end] = new_seg2_tbl

    # 2) 헤더 수정
    old_lim, = struct.unpack_from('<I', rom, SEG1_PAIR)
    new_lim = old_lim + n_extra
    struct.pack_into('<I', rom, SEG1_PAIR,     new_lim)   # seg1.lim
    struct.pack_into('<I', rom, SEG1_PAIR_DUP, new_lim)   # seg1 중복 쌍도 동기화
    struct.pack_into('<I', rom, SEG2_PAIR + 4, free_addr - HDR)  # seg2.off

    return (end + 3) & ~3
