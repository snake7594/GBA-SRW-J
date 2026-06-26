#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""슈퍼로봇대전 J — 아카이브 인덱스 재배치 모듈.

게임은 블록 주소를 (IDX_BASE + index[k]) 로 계산한다. 그래서 0x08F35000 같은
전투 텍스트 주소가 ROM 어디에도 리터럴로 없었다. 블록을 재배치하려면
index[k] = (새 파일오프셋 - IDX_BASE) 로 갱신하면 된다. (시나리오 패치와 동일 메커니즘.)

확정 상수:
  IDX_BASE = 0xE3097C  (= master_table[2] = 인덱스 배열 시작 = 오프셋 기준)
  인덱스 항목 = 373개 (0~372)
  전투 헤더 블록    = 인덱스 193
  전투 대사 블록    = 인덱스 194~370 (177개)
  코드표 블록       = 인덱스 371 (0xFB18B8)
  사운드/삼각 블록  = 인덱스 372 (0xFB19AC)
"""
import struct

IDX_BASE   = 0xE3097C
IDX_ARRAY  = 0xE3097C          # 인덱스 배열 시작(파일오프셋). 베이스와 동일.
NUM_ENTRIES= 373
GBA        = 0x08000000
GBA_MAX    = 0x2000000         # 32MB
# 마지막(372) 블록의 끝 = 사운드/삼각 테이블 끝. 비0 마지막+1 정렬.
LAST_BLOCK_END = 0xFB1C00

BATTLE_HEADER = 193
BATTLE_FIRST  = 194
BATTLE_LAST   = 370
CODETABLE_IDX = 371
SOUND_IDX     = 372


def read_index(rom, k):
    """index[k] 의 저장값(오프셋) 반환."""
    return struct.unpack_from('<I', rom, IDX_ARRAY + k*4)[0]

def write_index(rom, k, value):
    """index[k] 에 오프셋값 기록 (rom 은 bytearray)."""
    struct.pack_into('<I', rom, IDX_ARRAY + k*4, value & 0xFFFFFFFF)

def block_off(rom, k):
    """블록 k 의 현재 파일오프셋 = IDX_BASE + index[k]."""
    return IDX_BASE + read_index(rom, k)

def block_size(rom, k):
    """블록 k 의 크기. k<372 면 다음 블록 시작 - 시작. k==372 면 영역 끝까지."""
    s = block_off(rom, k)
    if k < NUM_ENTRIES - 1:
        return block_off(rom, k+1) - s
    return LAST_BLOCK_END - s

def block_bytes(rom, k):
    s = block_off(rom, k); n = block_size(rom, k)
    return bytes(rom[s:s+n])


def ensure_rom_capacity(rom, end_off):
    """rom(bytearray) 크기를 end_off 까지 담도록 2의 거듭제곱으로 확장, 0xFF 패딩.
    반환: (확장됨 여부, 새 크기)."""
    need = end_off
    cur = len(rom)
    if need <= cur:
        return False, cur
    size = 1
    while size < need:
        size <<= 1
    if size > GBA_MAX:
        raise ValueError(f"필요크기 0x{need:X} 가 GBA 최대 32MB(0x{GBA_MAX:X}) 초과")
    rom.extend(b'\xFF' * (size - cur))
    return True, size


def relocate_block(rom, k, dest_off):
    """블록 k 를 dest_off(파일오프셋)로 복사하고 index[k] 갱신. rom 은 bytearray.
    원본 위치는 그대로 둠(게임은 더 이상 거기서 읽지 않음). 반환: 블록 크기."""
    data = block_bytes(rom, k)
    n = len(data)
    if dest_off + n > len(rom):
        ensure_rom_capacity(rom, dest_off + n)
    rom[dest_off:dest_off+n] = data
    write_index(rom, k, dest_off - IDX_BASE)
    return n


def map_blocks(rom):
    """모든 블록의 (k, off, size) 리스트."""
    out=[]
    for k in range(NUM_ENTRIES):
        out.append((k, block_off(rom, k), block_size(rom, k)))
    return out


if __name__ == '__main__':
    import sys, hashlib
    rom = bytearray(open(sys.argv[1] if len(sys.argv)>1 else 'jp.gba','rb').read())
    orig_md5 = hashlib.md5(rom).hexdigest()
    print(f"ROM 크기 0x{len(rom):X}, md5 {orig_md5}")
    print(f"인덱스 항목 {NUM_ENTRIES}, IDX_BASE 0x{IDX_BASE:X}")
    bm = map_blocks(rom)
    print("주요 블록:")
    for k in [0,191,192,193,194,370,371,372]:
        _,o,sz = bm[k]
        print(f"  [{k}] off 0x{o:X}  size 0x{sz:X}")
