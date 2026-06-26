# -*- coding: utf-8 -*-
"""슈퍼로봇대전 J 전투 대사 한글 패치 적용 런처.

사용법:
  python 패치하기.py [입력ROM] [출력ROM]

  예) python 패치하기.py input.gba srwj_battle_kr.gba
  - 입력 생략 시 input.gba, 출력 생략 시 srwj_battle_kr.gba 사용
  - 입력 ROM은 '한글 폰트 + 시나리오 + 타이틀'이 이미 적용된 32MB ROM이어야 합니다.
"""
import sys, os
from srwj_battle_kr_insert import BattleKRInserter

JSON_PATH = 'battle_dialogue.json'

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    in_rom  = args[0] if len(args) > 0 else 'input.gba'
    out_rom = args[1] if len(args) > 1 else 'srwj_battle_kr.gba'

    if not os.path.exists(in_rom):
        print(f"[오류] 입력 ROM을 찾을 수 없습니다: {in_rom}")
        print("       한글 폰트+시나리오+타이틀이 적용된 32MB ROM을")
        print("       이 폴더에 input.gba 로 두거나, 파일명을 인자로 주세요.")
        print("       예) python 패치하기.py 내한글롬.gba")
        sys.exit(1)
    if not os.path.exists(JSON_PATH):
        print(f"[오류] 번역 데이터가 없습니다: {JSON_PATH}")
        sys.exit(1)

    sz = os.path.getsize(in_rom)
    print(f"입력 ROM : {in_rom} ({sz:,} bytes)")
    if sz != 33554432:
        print(f"  ※ 경고: 크기가 32MB(33,554,432)가 아닙니다. 올바른 한글 패치 ROM인지 확인하세요.")

    ins = BattleKRInserter(in_rom, JSON_PATH)
    print(f"번역 사전: unique {len(ins.uni)}개 적용")
    r = ins.build(out_rom)
    print(f"변경 블록: {r['changed']}/177, 번역 토큰: {r['tokens']}개")
    print(f"확장영역 0x{r['dest']:X}부터 0x{r['used']:X} 사용, ROM 0x{r['rom']:X}")
    print(f"\n완료! 저장됨: {out_rom}")
    print("mGBA 등 에뮬레이터나 실기에서 전투 대사가 한글로 나오는지 확인하세요.")

if __name__ == '__main__':
    main()
