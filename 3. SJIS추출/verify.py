# -*- coding: utf-8 -*-
"""패치 ROM 검증.

translations.json 의 번역(ko)이 패치 ROM에 제대로 들어갔는지 확인하고,
미완성 번역(카타카나/히라가나/장음 ー 잔존)을 찾아 알려준다.

    python verify.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import srwj_codec as codec

HERE     = os.path.dirname(os.path.abspath(__file__))
ROM_PATH = os.path.join(HERE, 'output', '슈퍼로봇대전J_한글.gba')
TRANS    = os.path.join(HERE, 'translations.json')
REPORT   = os.path.join(HERE, 'output', 'build_report.json')


def main():
    for p in (ROM_PATH, TRANS, REPORT):
        if not os.path.exists(p):
            print(f"[오류] 먼저 build_patch.py 를 실행하세요. (없음: {os.path.basename(p)})")
            return 1

    rom   = open(ROM_PATH, 'rb').read()
    data  = json.load(open(TRANS, encoding='utf-8'))['entries']
    rep   = json.load(open(REPORT, encoding='utf-8'))
    reloc = {it['off']: int(it['new_off'], 16) for it in rep['relocations']}

    mismatch, kana, garbage = [], [], []
    for e in data:
        off = int(e['off'], 16)
        src = reloc.get(e['off'], off)
        i = src
        while i < src + 90 and rom[i] != 0:
            i += 1
        seg  = rom[src:i]
        disp = codec.decode(seg, stop_at_null=True)

        if disp.replace('\u3000', ' ') != codec.normalize(e['ko']).replace('\u3000', ' '):
            mismatch.append((e['off'], e['ko'], disp))
        if codec.has_kana(seg):
            kana.append((e['off'], e['jp'], disp))
        # 슬롯 내 잔여 0x80
        j, end = off, off + e['len'] + 4
        while j < end:
            c = rom[j]
            if c == 0x00:
                break
            if c == 0x80:
                garbage.append((e['off'], disp)); break
            j += 2 if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) else 1

    print(f"항목 총 {len(data)}개")
    print(f"번역(ko) 반영 불일치 : {len(mismatch)}")
    print(f"잔여 0x80(■ 깨짐)     : {len(garbage)}")
    print(f"미완성(카나/장음 ー)  : {len(kana)}")
    print(f"재배치               : {rep['relocated']}  /  제자리: {rep['inplace']}")

    if mismatch:
        print("\n[불일치] (번역이 슬롯/패딩을 넘쳐 잘렸을 수 있음 → ko를 줄이세요)")
        for off, ko, disp in mismatch[:20]:
            print(f"   {off} ko={ko!r}  ROM={disp!r}")
    if kana:
        print("\n[미완성 번역] 아래 항목에 일본어 카나/장음(ー)이 남아있습니다. translations.json 에서 고치세요:")
        for off, jp, disp in kana:
            print(f"   {off} 원문={jp!r}  현재={disp!r}")
    if not mismatch and not garbage and not kana:
        print("\n모든 항목 정상.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
