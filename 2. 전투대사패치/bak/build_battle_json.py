# -*- coding: utf-8 -*-
"""슈퍼로봇대전 J 전투 대사 추출기 (마커 분리 + 위치/길이 포함 JSON 생성).

ROM의 전투 대사 블록(193~370)을 토큰 단위로 파싱한다. 모든 대사 토큰은
첫 1바이트가 0x00~0x06 범위의 '대사 시작 마커'로 시작한다(코드표상 ！・っいな、ー
로 디코드되지만, 번역과 무관한 제어 요소다). 이 마커를 별도 'lead' 필드로 분리해
번역(ko)에서 누락되지 않도록 한다.

엔트리 필드:
  off  : ROM 첫 출현 절대 파일오프셋
  len  : 원문이 차지한 바이트 길이(마커 1바이트 포함)
  blk  : 아카이브 블록 인덱스(193~370)
  lead : 대사 시작 마커(첫 1문자). 번역 무관·보존 전용. enc 시 0x00~0x06.
  jp   : 마커를 뗀 순수 원문(참고/매칭)
  ko   : 마커를 뗀 순수 한국어 번역  ★편집 대상★
  n/ptrs : 같은 대사가 여러 곳에 나올 때 출현 횟수·전체 위치
패치 시 enc(lead) + enc(ko) 로 재조립하므로 마커는 항상 보존된다.

사용법:
  python build_battle_json.py [입력ROM] [출력JSON] [참고JSON(raw->ko 소스)]
  기본값: input.gba  battle_dialogue.json  battle_dialogue.json
  ※ 참고JSON은 구형(jp=raw 통짜)·신형(lead/jp 분리) 모두 자동 인식.
"""
import sys, json, hashlib
from srwj_battle_codec import BattleCodec
import srwj_archive as A

FIRST, LAST = A.BATTLE_HEADER, A.BATTLE_LAST   # 193, 370 (블록193도 대사 포함)


def _mapping():
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
    """일본어 카나/한자가 남아있는지(미완성 검사). ・(U+30FB) 제외."""
    return any(('\u3040' <= c <= '\u30fa') or ('\u30fc' <= c <= '\u30ff')
               or ('\u4e00' <= c <= '\u9fff') for c in s)


def extract_tokens(rom, cx):
    """블록 193~370의 모든 'text' 토큰을 (off, blen, blk, cat, raw)로 반환."""
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

    def enc1(ch):
        try: return cx.enc_text(ch)[0]
        except Exception: return -1

    def split_marker(raw):
        """raw -> (lead, body). 첫 1문자가 0x00~0x06 마커면 분리."""
        if raw and 0x00 <= enc1(raw[0]) <= 0x06:
            return raw[0], raw[1:]
        return '', raw

    # 참고 JSON: raw(=lead+jp) -> ko_full, 그리고 body(마커뗀 원문) -> ko 두 맵.
    # 구형/신형 자동. unique({jp=body, tr}) 편집 마스터를 body 키로 매칭.
    KO = {}; KO_body = {}
    try:
        ref = json.load(open(ref_path, encoding='utf-8'))
        rents = ref['entries'] if isinstance(ref, dict) and 'entries' in ref else ref
        for x in rents:
            if 'lead' in x:                       # 신형(이미 분리)
                raw = x.get('lead', '') + x.get('jp', '')
                ko = x.get('ko', '')
                kof = (x.get('lead', '') + ko) if ko else ''
                if raw: KO[raw] = kof
                if x.get('jp', ''): KO_body.setdefault(x['jp'], ko or '')
            else:                                 # 구형 {jp, tr/ko} — jp가 raw일 수도 body일 수도
                jp = x.get('jp', '')
                kof = x.get('ko', x.get('tr', '')) or ''
                if jp:
                    KO.setdefault(jp, kof)        # jp가 raw(마커 포함)인 경우 대비
                    KO_body.setdefault(jp, kof)   # jp가 body(마커 뗀)인 경우 — unique 마스터
    except Exception:
        pass

    toks = extract_tokens(rom, cx)

    # raw 기준 그룹화(첫 출현 순서 보존)
    order = []; grp = {}
    for off, blen, blk, cat, raw in toks:
        if raw not in grp:
            grp[raw] = {'len': blen, 'blk': blk, 'offs': []}
            order.append(raw)
        grp[raw]['offs'].append(off)
        if blen != grp[raw]['len']:
            grp[raw]['len'] = max(grp[raw]['len'], blen)

    entries = []
    n_lead = n_trans = n_nondlg = n_unfilled = 0
    for raw in order:
        g = grp[raw]
        lead, body = split_marker(raw)
        if lead: n_lead += 1
        kof = KO.get(raw)
        if kof is None:                       # raw 매칭 실패 → body(마커뗀 원문)로 매칭
            kof = KO_body.get(body, '')
        kof = kof or ''
        # ko_body: 참고 ko에서 마커 흔적 제거(정확히 lead 와 같은 선두 1자만)
        if kof and lead and kof[:1] == lead:
            ko = kof[1:]
        else:
            ko = kof
        is_dlg = bool(body.strip('！\n\u3000・'))
        if is_dlg:
            n_trans += 1
            if not ko or jp_residual(ko): n_unfilled += 1
        else:
            n_nondlg += 1
        offs = sorted(g['offs'])
        e = {'off': f"0x{offs[0]:08X}", 'len': g['len'], 'blk': g['blk'],
             'lead': lead, 'jp': body, 'ko': ko}
        if len(offs) > 1:
            e['n'] = len(offs)
            e['ptrs'] = [f"0x{o:08X}" for o in offs]
        entries.append(e)

    readme = (
        "전투(배틀) 대사 추출·검증 데이터. 'ko'(한국어 번역)만 고치면 됩니다. "
        "lead=대사 시작 마커(첫 1바이트, 코드표상 ！・っいな、ー로 보이지만 번역과 무관한 "
        "제어 요소이니 그대로 두세요. 패치 때 자동으로 보존됩니다). jp=마커를 뗀 순수 원문"
        "(매칭/검증 기준, 수정 금지). ko=마커를 뗀 순수 번역. off=ROM 첫 출현 절대 파일오프셋, "
        "len=원문이 차지한 바이트 길이(마커 1바이트 포함, 한글 1자=2바이트). n/ptrs=같은 대사가 "
        "여러 곳에 나올 때 출현 횟수와 전체 위치(없으면 1곳=off). 패치는 enc(lead)+enc(ko)로 "
        "재조립해 마커가 절대 누락되지 않습니다. 줄바꿈=\\n, [7d]~[80]은 이름/변수 인라인코드이니 "
        "위치 그대로 두세요. 공백은 전각으로 자동 변환됩니다. ko가 빈 항목은 기호/효과음 등 "
        "번역 불필요한 비대사입니다. 카타카나/히라가나가 ko에 남아있으면 미완성 번역입니다."
    )

    doc = {
        '_README': readme,
        'rom_md5': md5,
        'idx_base': f"0x{A.IDX_BASE:X}",
        'block_range': [FIRST, LAST],
        'count': len(entries),
        'total_tokens': len(toks),
        'with_lead': n_lead,
        'translatable': n_trans,
        'non_dialogue': n_nondlg,
        'entries': entries,
    }
    _write_json(doc, out_path)

    print(f"ROM        : {rom_path}  (md5 {md5})")
    print(f"전체 토큰  : {len(toks):,}")
    print(f"고유 대사  : {len(entries):,}  (마커보유 {n_lead} / 번역대상 {n_trans} / 비대사 {n_nondlg})")
    print(f"마커 없는 항목: {len(entries)-n_lead}")
    print(f"미채움(대사·ko공란/카나): {n_unfilled}")
    print(f"저장        : {out_path}")
    return doc


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('-')]
    rom_path = a[0] if len(a) > 0 else 'input.gba'
    out_path = a[1] if len(a) > 1 else 'battle_dialogue.json'
    ref_path = a[2] if len(a) > 2 else 'battle_dialogue.json'
    build(rom_path, out_path, ref_path)
