# -*- coding: utf-8 -*-
"""전투 대사 줄바꿈 (개정):
- 결과물 첫 줄 본문 ≤8자 (화자명 최대5 + 꺽쇠「」2 = 7자가 첫 줄에서 대사 외 차지 → 15-7=8)
- 둘째 줄부터 ≤15자
- 공백 경계 우선, 없으면 글자 단위로 강제 분할(단어가 잘려도 개행)
- [xx] 이름변수는 통째(VARLEN=5: 이름 최대 5자 보수 산정), \n(의미개행) 존중
- 박스 최대 3줄
"""
import json, re
MARK=re.compile(r'\[[0-9a-f]{2}\]')
LIMIT_FIRST=8; LIMIT_REST=15; VARLEN=5

def units(s):
    u=[]; i=0
    while i<len(s):
        m=MARK.match(s,i)
        if m: u.append(m.group(0)); i=m.end()
        else: u.append(s[i]); i+=1
    return u
def ulen(t): return VARLEN if MARK.fullmatch(t) else 1
def linelen(s): return sum(ulen(t) for t in units(s))

def wrap_units(toks, first_limit, rest_limit):
    lines=[]; cur=[]; last_sp=-1
    def lim(): return first_limit if not lines else rest_limit
    def L(): return sum(ulen(t) for t in cur)
    for t in toks:
        cur.append(t)
        if t in ('\u3000',' '): last_sp=len(cur)-1
        while L()>lim():
            if 0<last_sp<len(cur):
                lines.append(''.join(cur[:last_sp])); cur=cur[last_sp+1:]; last_sp=-1
            elif len(cur)>1:
                last=cur.pop(); lines.append(''.join(cur)); cur=[last]; last_sp=-1
            else:
                break   # 단일 토큰([xx])이 한도 초과 → 분할 불가
    if cur: lines.append(''.join(cur))
    return [s for s in (x.strip('\u3000 ') for x in lines) if s!='']

def rewrap_keepnl(tr):
    out=[]
    for line in tr.split('\n'):
        if line=='': out.append(''); continue
        fl = LIMIT_FIRST if not out else LIMIT_REST
        out.extend(wrap_units(units(line), fl, LIMIT_REST))
    return '\n'.join(out)

def rewrap_flat(tr):
    flat=re.sub(r'[\u3000 ]+','\u3000', tr.replace('\n','\u3000')).strip('\u3000 ')
    return '\n'.join(wrap_units(units(flat), LIMIT_FIRST, LIMIT_REST))

if __name__=='__main__':
    data=json.load(open('battle_dialogue_unique.json',encoding='utf-8'))
    def first_len(s): return linelen(s.split('\n')[0]) if s else 0
    def max_rest(s):
        ls=s.split('\n'); return max((linelen(l) for l in ls[1:]), default=0)
    # 1) 첫 줄 8자 / 이후 15자로 전체 재줄바꿈
    c1=0
    for x in data:
        tr=x.get('tr','')
        if not tr.strip(): continue
        nt=rewrap_keepnl(tr)
        if nt!=tr: x['tr']=nt; c1+=1
    # 2) 4줄 이상은 \n 풀어 전체 greedy로 압축(첫 줄 8 유지)
    c2=0
    for x in data:
        tr=x.get('tr','')
        if tr.strip() and tr.count('\n')>=3:
            nt=rewrap_flat(tr)
            if nt!=tr: x['tr']=nt; c2+=1
    json.dump(data,open('battle_dialogue_unique.json','w',encoding='utf-8'),ensure_ascii=False)
    # 집계
    over_first=sum(1 for x in data if x.get('tr','').strip() and first_len(x['tr'])>8)
    over_rest=sum(1 for x in data if x.get('tr','').strip() and max_rest(x['tr'])>15)
    nl={}
    for x in data:
        tr=x.get('tr','')
        if tr.strip(): k=tr.count('\n')+1; nl[k]=nl.get(k,0)+1
    print(f"재줄바꿈 {c1}개, 4줄+압축 {c2}개")
    print(f"첫 줄 8자 초과: {over_first} | 2줄+ 15자 초과: {over_rest}")
    print(f"줄 수 분포: {dict(sorted(nl.items()))}")
    # 4줄+ 잔여
    rest4=[x for x in data if x.get('tr','').strip() and x['tr'].count('\n')>=3]
    print(f"여전히 4줄+: {len(rest4)}개")
    for x in rest4[:20]:
        print("  "+repr(x['tr']))
