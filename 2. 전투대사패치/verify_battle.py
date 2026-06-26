# -*- coding: utf-8 -*-
"""슈퍼로봇대전 J 전투 대사 JSON 검증 도구.

battle_dialogue.json 이 ROM에서 올바르게 추출됐는지, 놓친 대사가 없는지 검사한다.

검사 항목:
  [A] 추출 정확성 : 각 엔트리의 jp(원문)를 인코딩한 바이트가, off 및 모든 ptrs 위치의
                    ROM 바이트와 정확히 일치하고 그 길이가 len 과 같은지.
  [B] 완전성(누락): ROM 전투블록(193~370)을 다시 전수 파싱해 얻은 모든 대사 토큰이
                    JSON에 빠짐없이 들어있는지(누락/잉여 오프셋 검출).
  [C] 개수 정합   : entries 수=count, 출현 합(Σn)=total_tokens 인지.
  [D] 번역 상태   : 미완성(ko에 카나/한자 잔존), 미번역(대사인데 ko 공란) 집계.

사용법:
  python verify_battle.py [ROM] [JSON]
  기본값: input.gba  battle_dialogue.json
"""
import sys, json
from srwj_battle_codec import BattleCodec
from build_battle_json import _mapping, jp_residual, extract_tokens, FIRST, LAST


def verify(rom_path, json_path):
    rom = bytearray(open(rom_path, 'rb').read())
    cx = BattleCodec(rom); cx.set_gaiji(_mapping())
    doc = json.load(open(json_path, encoding='utf-8'))
    ents = doc['entries']
    print(f"ROM  : {rom_path}")
    print(f"JSON : {json_path}  (블록 {FIRST}~{LAST})")
    print(f"엔트리 {len(ents):,} / 메타 count={doc.get('count')} "
          f"total_tokens={doc.get('total_tokens')}\n")

    # [A] 추출 정확성 — off/ptrs 위치의 ROM 바이트 == enc(lead+jp), 길이 == len
    a_ok = a_bad = a_occ = 0
    a_samples = []
    for e in ents:
        raw = e.get('lead', '') + e['jp']   # 원본 = 마커(lead) + 본문(jp)
        ln = e['len']
        try:
            enc = cx.enc_text(raw)
        except Exception:
            enc = None
        offs = [int(e['off'], 16)]
        offs += [int(p, 16) for p in e.get('ptrs', []) if int(p, 16) != offs[0]]
        good = (enc is not None and len(enc) == ln)
        for o in offs:
            a_occ += 1
            if good and bytes(rom[o:o+ln]) == enc:
                a_ok += 1
            else:
                a_bad += 1
                if len(a_samples) < 6:
                    a_samples.append((e['off'], raw[:24]))
    print(f"[A] 추출 정확성 : 출현 {a_occ:,}곳 중 일치 {a_ok:,} / 불일치 {a_bad}")
    for off, jp in a_samples:
        print(f"      ✗ {off}  {jp!r}")

    # [B] 완전성 — ROM 전수 토큰의 오프셋이 JSON에 모두 존재하는지
    toks = extract_tokens(rom, cx)
    rom_offs = {off for off, _, _, _, _ in toks}
    json_offs = set()
    for e in ents:
        json_offs.add(int(e['off'], 16))
        for p in e.get('ptrs', []):
            json_offs.add(int(p, 16))
    missing = rom_offs - json_offs        # ROM에 있는데 JSON에 없음(누락!)
    extra = json_offs - rom_offs          # JSON에 있는데 ROM에 없음(유령)
    print(f"\n[B] 완전성(누락) : ROM 토큰 {len(toks):,} / 고유위치 {len(rom_offs):,}")
    print(f"      누락(ROM에만) {len(missing)} / 잉여(JSON에만) {len(extra)}")
    for o in list(missing)[:6]:
        print(f"      ✗ 누락 0x{o:08X}")

    # [C] 개수 정합
    sigma_n = sum(e.get('n', 1) for e in ents)
    c1 = (len(ents) == doc.get('count'))
    c2 = (sigma_n == doc.get('total_tokens') == len(toks))
    print(f"\n[C] 개수 정합   : entries==count {'OK' if c1 else 'FAIL'} | "
          f"Σn==total_tokens=={len(toks)} {'OK' if c2 else 'FAIL'} (Σn={sigma_n:,})")

    # [E] 마커 무결성 — 모든 엔트리의 lead 가 0x00~0x06 으로 인코딩되는지, 누락 0 인지
    no_lead = [e for e in ents if not e.get('lead', '')]
    bad_lead = []
    for e in ents:
        lead = e.get('lead', '')
        if lead:
            try:
                c = cx.enc_text(lead)[0]
            except Exception:
                c = -1
            if not (0x00 <= c <= 0x06):
                bad_lead.append((e['off'], lead, c))
    print(f"\n[E] 마커 무결성 : 마커 없는 엔트리 {len(no_lead)} / 마커코드 범위밖(0x00~06 아님) {len(bad_lead)}")
    for off, lead, c in bad_lead[:5]:
        print(f"      ✗ {off}  lead={lead!r} -> 0x{c:02X}")
    for e in no_lead[:5]:
        print(f"      ✗ 마커없음 {e['off']}  jp={e['jp'][:24]!r}")

    # [D] 번역 상태 (비대사=카나/한자 없는 본문은 미번역에서 제외)
    unfinished = [e for e in ents if e['ko'] and jp_residual(e['ko'])]
    untranslated = [e for e in ents
                    if not e['ko'] and jp_residual(e['jp'])]
    translated = [e for e in ents if e['ko'] and not jp_residual(e['ko'])]
    nondlg = [e for e in ents if not jp_residual(e['jp']) and not e['ko']]
    print(f"\n[D] 번역 상태   : 번역완료 {len(translated):,} / 미번역(대사·ko공란) "
          f"{len(untranslated)} / 미완성(카나잔존) {len(unfinished)} / 비대사·기호 {len(nondlg)}")
    for e in unfinished[:5]:
        print(f"      ⚠ 카나잔존 {e['off']}  ko={e['ko'][:24]!r}")
    for e in untranslated[:5]:
        print(f"      ⚠ 미번역  {e['off']}  jp={e['jp'][:24]!r}")

    ok = (a_bad == 0 and not missing and not extra and c1 and c2
          and not unfinished and not no_lead and not bad_lead)
    print(f"\n{'═'*46}")
    print("결과: ✅ 전부 통과" if ok else "결과: ⚠ 위 항목 확인 필요")
    return ok


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('-')]
    rom = a[0] if len(a) > 0 else 'input.gba'
    js = a[1] if len(a) > 1 else 'battle_dialogue.json'
    verify(rom, js)
