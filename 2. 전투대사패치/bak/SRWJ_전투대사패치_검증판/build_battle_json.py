# -*- coding: utf-8 -*-
"""슈퍼로봇대전 J 전투 대사 추출기 (위치/길이 포함 JSON 생성).

ROM의 전투 대사 블록(아카이브 인덱스 194~370)을 토큰 단위로 직접 파싱해,
각 대사가 ROM 어디(off)에 있고 원문이 몇 바이트(len)였는지, 몇 번 출현(n/ptrs)하는지
를 기록한 검증용 JSON(battle_dialogue.json)을 만든다.

- 'jp' = ROM에 실제로 들어있는 원문 텍스트 그대로(선두 ！ 포함). enc(jp) 는 정확히
  len 바이트이며 ROM[off:off+len] 와 바이트 단위로 일치한다(추출 정확성의 근거).
- 'ko' = 한국어 번역. 기존 battle_dialogue_unique.json(jp정규화→tr) 사전과
  마징가계(kouji_tr) 폴백으로 자동 채운다. 비대사(기호/효과음)는 공란.

사용법:
  python build_battle_json.py [입력ROM] [출력JSON] [참고사전JSON]
  기본값: input.gba  battle_dialogue.json  battle_dialogue_unique.json
"""
import sys, json, hashlib
from srwj_battle_codec import BattleCodec
import srwj_archive as A
try:
    import kouji_tr as K   # 마징가계 컴포넌트 폴백(있으면 사용)
except Exception:
    K = None

FIRST, LAST = A.BATTLE_HEADER, A.BATTLE_LAST   # 193, 370 (블록193도 대사 포함)


def _mapping():
    """KS X 1001 한글 2350자 ↔ SJIS L1 한자 슬롯 매핑(가이지 역디코드용)."""
    hanguls = [bytes([0xB0+i//94, 0xA1+i%94]).decode('euc-kr') for i in range(2350)]
    sj = []; hi, lo = 0x88, 0x9f
    while len(sj) < 2350:
        try:
            if '\u4e00' <= bytes([hi, lo]).decode('cp932') <= '\u9fff':
                sj.append((hi, lo))
        except Exception:
            pass
        lo += 1
        if lo == 0x7f: lo = 0x80
        if lo > 0xfc: lo = 0x40; hi += 1
    return {hanguls[i]: list(sj[i]) for i in range(2350)}


def _write_json(doc, path):
    """indent=1 로 저장하되 'ptrs' 배열(hex 문자열 목록)만 한 줄로 압축."""
    import re
    txt = json.dumps(doc, ensure_ascii=False, indent=1)
    def _compact(m):
        items = re.findall(r'"0x[0-9A-Fa-f]+"', m.group(0))
        return '"ptrs": [' + ', '.join(items) + ']'
    txt = re.sub(r'"ptrs": \[[^\]]*\]', _compact, txt)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(txt)


def jp_residual(s):
    """일본어 카나/한자가 남아있는지(번역 대상 판정 / 미완성 검사)."""
    return any(('\u3040' <= c <= '\u30fa') or ('\u30fc' <= c <= '\u30ff')
               or ('\u4e00' <= c <= '\u9fff') for c in s)


def extract_tokens(rom, cx):
    """블록 194~370을 파싱해 모든 'text' 토큰을 (off, blen, blk, cat, raw)로 반환.

    왕복 항등(rebuild(parse(b))==b)이 보장되므로, 토큰별 rebuild 길이를 누적해
    각 토큰의 블록 내 시작 오프셋을 정확히 역산한다.
    """
    out = []
    for k in range(FIRST, LAST + 1):
        bo = cx.blkoff(rom, k); be = cx.blkoff(rom, k + 1)
        b = rom[bo:be]
        u16 = lambda o: b[o] | (b[o+1] << 8)
        pairs = [(u16(i*4), u16(i*4+2)) for i in range(10)]
        offs = [p[0] for p in pairs]; counts = [p[1] for p in pairs]
        entries = [(offs[i]+e*8, u16(offs[i]+e*8+2))
                   for i in range(10) for e in range(counts[i])]
        if not entries:
            continue
        bounds = sorted(set(t for _, t in entries)) + [len(b)]
        # textOffset -> 카테고리(최초 참조 기준)
        to_cat = {}
        for i in range(10):
            for e in range(counts[i]):
                t = u16(offs[i]+e*8+2); to_cat.setdefault(t, i)
        for j in range(len(bounds)-1):
            seg_start = bounds[j]; seg = b[seg_start:bounds[j+1]]
            cat = to_cat.get(seg_start, -1)
            pos = 0
            for t in cx.parse(seg):
                blen = len(cx.rebuild([t]))
                if t[0] == 't':
                    out.append((bo+seg_start+pos, blen, k, cat, t[1]))
                pos += blen
    return out


def build(rom_path, out_path, ref_path):
    rom = bytearray(open(rom_path, 'rb').read())
    cx = BattleCodec(rom); cx.set_gaiji(_mapping())
    md5 = hashlib.md5(rom).hexdigest()

    toks = extract_tokens(rom, cx)

    # 참고 사전: jp(정규화 key) -> tr
    D = {}
    try:
        ref = json.load(open(ref_path, encoding='utf-8'))
        D = {x['jp']: x['tr'] for x in ref if x.get('tr', '').strip()}
    except Exception:
        pass

    def fill_ko(raw):
        """raw 토큰 -> 한국어 번역(선두 ！ 재부착). 못 채우면 '' 반환.
        판정/순서는 기존 srwj_battle_kr_insert.tr_token 과 동일하게 유지한다."""
        if not raw.strip('！\n\u3000・'):
            return ''                       # 기호/공백/제어만 → 비대사
        lead = len(raw) - len(raw.lstrip('！'))
        key = raw[lead:]
        tr = D.get(key)
        if tr is not None and not jp_residual(tr):
            return '！'*lead + tr
        if K is not None:                   # 마징가계 폴백(부분치환)
            try:
                kr = K.translate(raw)
                if not jp_residual(kr) and kr != raw:
                    return kr
            except Exception:
                pass
        return ''

    # raw 기준 그룹화(출현 위치 수집). 첫 출현 순서를 보존.
    order = []
    grp = {}
    for off, blen, blk, cat, raw in toks:
        if raw not in grp:
            grp[raw] = {'len': blen, 'blk': blk, 'cat': cat, 'offs': []}
            order.append(raw)
        grp[raw]['offs'].append(off)
        # 동일 raw 는 항상 동일 len (검증됨). 혹시 다르면 최댓값 보존.
        if blen != grp[raw]['len']:
            grp[raw]['len'] = max(grp[raw]['len'], blen)

    entries = []
    n_trans = n_nondlg = 0
    for raw in order:
        g = grp[raw]
        ko = fill_ko(raw)
        is_dlg = bool(raw.strip('！\n\u3000・'))
        if is_dlg: n_trans += 1
        else: n_nondlg += 1
        offs = sorted(g['offs'])
        e = {
            'off': f"0x{offs[0]:08X}",
            'len': g['len'],
            'blk': g['blk'],
            'jp':  raw,
            'ko':  ko,
        }
        if len(offs) > 1:
            e['n'] = len(offs)
            e['ptrs'] = [f"0x{o:08X}" for o in offs]
        entries.append(e)

    readme = (
        "전투(배틀) 대사 추출·검증 데이터. 'ko'(한국어 번역)만 고치면 됩니다. "
        "jp=ROM에 실제로 들어있는 원문 그대로(선두 '!'(전각) 포함, 참고/매칭 키). "
        "off=이 대사가 ROM에 처음 등장하는 절대 파일오프셋, len=원문이 차지한 바이트 길이"
        "(한글1자=2바이트). n/ptrs=같은 대사가 ROM 여러 곳에 나올 때의 출현 횟수와 전체 위치"
        "(없으면 1곳=off). 패치는 블록(인덱스 194~370)을 통째로 재구성해 길어진 블록만 "
        "ROM 확장영역에 재배치하므로, ko가 len보다 길어도 됩니다(슬롯 길이 제약 없음). "
        "줄바꿈=\\n, [7d]~[80]은 이름/변수 인라인코드이니 위치 그대로 두세요. 공백은 전각으로 "
        "자동 변환됩니다. ko가 빈 항목은 기호/효과음 등 번역 불필요한 비대사이니 원본을 유지합니다. "
        "카타카나/히라가나가 남아있으면 미완성 번역입니다."
    )

    doc = {
        '_README': readme,
        'rom_md5': md5,
        'idx_base': f"0x{A.IDX_BASE:X}",
        'block_range': [FIRST, LAST],
        'count': len(entries),
        'total_tokens': len(toks),
        'translatable': n_trans,
        'non_dialogue': n_nondlg,
        'entries': entries,
    }
    _write_json(doc, out_path)

    # 참고: 사전엔 있으나 이 ROM엔 없는 항목(검증 보조)
    rom_keys = set()
    for raw in order:
        lead = len(raw) - len(raw.lstrip('！'))
        rom_keys.add(raw[lead:])
    not_in_rom = [{'jp': k, 'ko': v} for k, v in D.items() if k not in rom_keys]
    with open('_not_in_rom.json', 'w', encoding='utf-8') as f:
        json.dump({'_README': '참고 사전엔 있으나 이 ROM 전투블록엔 존재하지 않는 항목'
                              '(타 버전 ROM 잔재/깨진 데이터 추정). 패치 대상 아님.',
                   'count': len(not_in_rom), 'entries': not_in_rom},
                  f, ensure_ascii=False, indent=1)

    print(f"ROM        : {rom_path}  (md5 {md5})")
    print(f"전체 토큰  : {len(toks):,}")
    print(f"고유 대사  : {len(entries):,}  (번역대상 {n_trans:,} / 비대사 {n_nondlg})")
    print(f"저장        : {out_path}")
    print(f"참고(미존재): _not_in_rom.json  ({len(not_in_rom):,}건)")
    return doc


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('-')]
    rom_path = a[0] if len(a) > 0 else 'input.gba'
    out_path = a[1] if len(a) > 1 else 'battle_dialogue.json'
    ref_path = a[2] if len(a) > 2 else 'battle_dialogue_unique.json'
    build(rom_path, out_path, ref_path)
