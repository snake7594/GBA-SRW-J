# -*- coding: utf-8 -*-
"""전투 대사 번역(tr/ko) 줄바꿈 재정렬 — 시나리오와 동일 규칙(WIDTH=14).

규칙:
  - 모든 글자 폭 1. [7d]~[80] 등 이름/변수 인라인코드는 원문자처럼 5(VARLEN).
  - 한 줄 최대 14(DISPLAY_WIDTH).
  - 첫 줄: 화자명(≤5)+「」(2)=7 예약 → 순수 대사 ≤7.
  - 마지막 줄: 닫는 괄호 1 예약 → ≤13.
  - 띄어쓰기 경계 우선, 한 단어가 한도를 넘으면 글자 단위로 강제 분할.
  - 기존 \n 은 모두 풀고(flat) 규칙대로 다시 채워, 한 줄에 들어갈 수 있는데
    개행돼 있던 불필요한 \n 을 제거한다.
"""
import re

MARK = re.compile(r'\[[0-9a-f]{2}\]')
PAREN = re.compile(r'\([가-힣]{1,2}\)')   # (으)(이)(과)(들) 등 조사 괄호 — 쪼개지 않음
WIDTH = 14
LIMIT_FIRST = WIDTH - 7   # 7
LIMIT_REST  = WIDTH       # 14
LIMIT_LAST  = WIDTH - 1   # 13
VARLEN = 5


def units(s):
    u = []; i = 0
    while i < len(s):
        m = MARK.match(s, i)
        if m: u.append(m.group(0)); i = m.end(); continue
        m = PAREN.match(s, i)
        if m: u.append(m.group(0)); i = m.end(); continue
        u.append(s[i]); i += 1
    return u


def ulen(t):
    if MARK.fullmatch(t): return VARLEN
    if PAREN.fullmatch(t): return len(t)   # 괄호+글자 폭 그대로(분할만 방지)
    return 1


def linelen(s):
    return sum(ulen(t) for t in units(s))


def _greedy(toks, first_limit, rest_limit):
    """공백 경계 우선 greedy 줄바꿈. 단어가 한도 초과면 글자 단위 분할."""
    lines = []; cur = []; last_sp = -1
    def lim(): return first_limit if not lines else rest_limit
    def L(): return sum(ulen(t) for t in cur)
    for t in toks:
        cur.append(t)
        if t in ('\u3000', ' '): last_sp = len(cur) - 1
        while L() > lim():
            if 0 < last_sp < len(cur):
                lines.append(''.join(cur[:last_sp])); cur = cur[last_sp+1:]; last_sp = -1
            elif len(cur) > 1:
                last = cur.pop(); lines.append(''.join(cur)); cur = [last]; last_sp = -1
            else:
                break   # 단일 토큰([xx])이 한도 초과 → 분할 불가
    if cur: lines.append(''.join(cur))
    return [s for s in (x.strip('\u3000 ') for x in lines) if s != '']


def rewrap(tr):
    """tr 의 \n 을 모두 풀고 14폭 규칙으로 재줄바꿈(첫 7 / 중간 14 / 마지막 13)."""
    if not tr or not tr.strip():
        return tr
    # 1글자 조사 괄호 다음의 개행은 공백 없이 뒤 글자에 붙임: (으)\n로 -> (으)로
    s = re.sub(r'(\([가-힣]\))[\u3000 ]*\n[\u3000 ]*(?=[가-힣])', r'\1', tr)
    # 나머지 \n(주변 공백 포함)만 반각공백 하나로 — 본문 내 기존 공백 종류는 보존
    flat = re.sub(r'[\u3000 ]*\n[\u3000 ]*', ' ', s).strip('\u3000 ')
    lines = _greedy(units(flat), LIMIT_FIRST, LIMIT_REST)
    # 마지막 줄(닫는 괄호 자리) 13 초과 시 그 줄만 13 한도로 재분할
    if len(lines) >= 2 and linelen(lines[-1]) > LIMIT_LAST:
        tail = _greedy(units(lines[-1]), LIMIT_LAST, LIMIT_LAST)
        lines = lines[:-1] + tail
    return '\n'.join(lines)


if __name__ == '__main__':
    import json, sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'battle_dialogue_unique.json'
    field = sys.argv[2] if len(sys.argv) > 2 else 'tr'
    data = json.load(open(path, encoding='utf-8'))
    ents = data if isinstance(data, list) else data.get('entries', [])

    changed = 0
    for x in ents:
        tr = x.get(field, '') or ''
        if not tr.strip(): continue
        nt = rewrap(tr)
        if nt != tr:
            x[field] = nt; changed += 1

    # list 면 그대로, dict(엔트리 포함)면 그대로 저장
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False)

    # 검증 집계
    def first_len(s): return linelen(s.split('\n')[0]) if s else 0
    def mid_max(s):
        ls = s.split('\n'); return max((linelen(l) for l in ls[1:-1]), default=0) if len(ls) >= 3 else 0
    def last_len(s):
        ls = s.split('\n'); return linelen(ls[-1]) if len(ls) >= 2 else 0
    of = sum(1 for x in ents if x.get(field, '').strip() and first_len(x[field]) > LIMIT_FIRST)
    om = sum(1 for x in ents if x.get(field, '').strip() and mid_max(x[field]) > LIMIT_REST)
    ol = sum(1 for x in ents if x.get(field, '').strip() and last_len(x[field]) > LIMIT_LAST)
    nl = {}
    for x in ents:
        t = x.get(field, '')
        if t.strip(): k = t.count('\n') + 1; nl[k] = nl.get(k, 0) + 1
    print(f"파일: {path}  필드: {field}")
    print(f"재줄바꿈: {changed}개")
    print(f"규칙위반 → 첫줄>{LIMIT_FIRST}: {of} / 중간>{LIMIT_REST}: {om} / 마지막>{LIMIT_LAST}: {ol}")
    print(f"줄 수 분포: {dict(sorted(nl.items()))}")
