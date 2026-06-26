# -*- coding: utf-8 -*-
"""슈퍼로봇대전 J 전투 대사 전 블록(194~370) 한글 삽입 도구.
- 매핑: KS X 1001 한글 ↔ SJIS L1 한자 (폰트가 한글로 렌더)
- 블록 구조: 10쌍 헤더 + cat0~9 포인터테이블(8B엔트리) + 텍스트풀
- 토큰 단위 번역(선두 ！ 제거해 unique 매칭, 재부착), 포인터 textOffset 재계산
- 변경된 블록만 확장영역에 순차 재배치, 인덱스 갱신
- 무번역 토큰/비대사는 원본 바이트 유지(왕복 항등)
"""
import json, struct, re
from srwj_battle_codec import BattleCodec
import srwj_archive as A
# (kouji_tr 폴백은 build_battle_json.py 단계에서 ko에 반영되므로 여기선 불필요)

FIRST, LAST = 193, 370
MARK=re.compile(r'\[[0-9a-f]{2}\]')

def _mapping():
    hanguls=[bytes([0xB0+i//94,0xA1+i%94]).decode('euc-kr') for i in range(2350)]
    sj=[]; hi,lo=0x88,0x9f
    while len(sj)<2350:
        try:
            if '\u4e00'<=bytes([hi,lo]).decode('cp932')<='\u9fff': sj.append((hi,lo))
        except: pass
        lo+=1
        if lo==0x7f: lo=0x80
        if lo>0xfc: lo=0x40; hi+=1
    return {hanguls[i]:list(sj[i]) for i in range(2350)}

class BattleKRInserter:
    def __init__(self, rom_path, json_path):
        self.rom=bytearray(open(rom_path,'rb').read())
        self.cx=BattleCodec(self.rom)
        self.cx.set_gaiji(_mapping())
        doc=json.load(open(json_path, encoding='utf-8'))
        ents = doc['entries'] if isinstance(doc, dict) and 'entries' in doc else doc
        # battle_dialogue.json: jp=ROM 원문 그대로(raw) → ko 직접 매핑.
        # ko 가 비었거나(비대사) 일본어 잔존(미완성)이면 매핑에서 제외 → 원본 유지.
        self.uni={}
        for x in ents:
            jp=x.get('jp'); ko=x.get('ko','')
            if jp is None or not ko or not ko.strip(): continue
            if self.hjs(ko): continue
            self.uni[jp]=ko

    def normalize(self, s):
        out=[]
        for p in re.split(r'(\[[0-9a-f]{2}\])', s):
            if MARK.fullmatch(p): out.append(p); continue
            p=p.replace('…','・・・').replace('...','・・・')
            p=p.replace('—','―').replace('–','―')   # em/en dash → 전각 가로줄(SJIS 가능)
            q=[]
            for ch in p:
                o=ord(ch)
                if ch=='~': q.append('\u301c')
                elif ch=='-': q.append('\u2212')      # 하이픈마이너스 → 전각 마이너스(SJIS 가능)
                elif 0x21<=o<=0x7d: q.append(chr(o+0xFEE0))
                elif ch==' ': q.append('\u3000')
                else: q.append(ch)
            out.append(''.join(q))
        return ''.join(out)

    @staticmethod
    def hjs(s):  # ・(U+30FB) 제외 일본어 잔존
        return any(('\u3040'<=c<='\u30fa')or('\u30fc'<=c<='\u30ff')or('\u4e00'<=c<='\u9fff') for c in s)

    def tr_token(self, text):
        ko=self.uni.get(text)             # ROM 원문(raw) 직접 매핑
        if ko is None: return None        # 매핑 없음 → 원본 바이트 유지
        return self.normalize(ko)         # (선두 ！·폴백은 JSON ko에 이미 반영됨)

    def rebuild_block(self, b, apply_tr=True):
        u16=lambda o: b[o]|(b[o+1]<<8)
        pairs=[(u16(i*4),u16(i*4+2)) for i in range(10)]
        counts=[p[1] for p in pairs]; offs=[p[0] for p in pairs]
        pool_start=offs[9]+counts[9]*8
        entries=[(offs[i]+e*8, u16(offs[i]+e*8+2)) for i in range(10) for e in range(counts[i])]
        if not entries: return bytes(b), 0
        bounds=sorted(set(t for _,t in entries))+[len(b)]
        newpool=bytearray(b[pool_start:bounds[0]]); newmap={}; cur=pool_start+len(newpool); n=0
        for j in range(len(bounds)-1):
            seg=b[bounds[j]:bounds[j+1]]; newmap[bounds[j]]=cur
            out=bytearray()
            for t in self.cx.parse(seg):
                if t[0]=='t' and apply_tr:
                    kr=self.tr_token(t[1])
                    if kr is not None:
                        try:
                            enc=self.cx.enc_text(kr); out+=enc; n+=1; continue
                        except Exception: pass
                out+=self.cx.rebuild([t])
            newpool+=out; cur+=len(out)
        nb=bytearray(b[:pool_start])
        for eo,told in entries: struct.pack_into('<H', nb, eo+2, newmap[told])
        nb+=newpool
        return bytes(nb), n

    def find_free(self, need, start=0x1000000, end=0x2000000):
        i=start; run=0; rs=start; step=0x100
        while i<end:
            chunk=self.rom[i:i+step]
            if all(x in (0,0xff) for x in chunk):
                if run==0: rs=i
                run+=len(chunk)
                if run>=need+0x200: return (rs+0xF)&~0xF
            else: run=0
            i+=step
        return None

    def build(self, out_path):
        # 1) 항등 self-test
        for k in (FIRST, 250, 329, LAST):
            b=self.rom[self.cx.blkoff(self.rom,k):self.cx.blkoff(self.rom,k+1)]
            idb,_=self.rebuild_block(b, apply_tr=False)
            assert idb==b, f"블록{k} 항등 실패"
        # 2) 전 블록 재구성
        changed={}; tot_tok=0
        for k in range(FIRST, LAST+1):
            b=self.rom[self.cx.blkoff(self.rom,k):self.cx.blkoff(self.rom,k+1)]
            nb,n=self.rebuild_block(b, apply_tr=True)
            if n>0 and nb!=b: changed[k]=nb; tot_tok+=n
        # 3) 변경 블록 확장영역 순차 배치
        total=sum(len(v) for v in changed.values())
        dest=self.find_free(total)
        assert dest, f"확장영역 빈공간 부족(필요 0x{total:X})"
        cur=dest
        for k in sorted(changed):
            nb=changed[k]
            self.rom[cur:cur+len(nb)]=nb
            A.write_index(self.rom, k, cur - A.IDX_BASE)
            cur=(cur+len(nb)+0xF)&~0xF
        open(out_path,'wb').write(self.rom)
        return {'changed':len(changed), 'tokens':tot_tok, 'dest':dest,
                'used':cur-dest, 'rom':len(self.rom)}

if __name__=='__main__':
    import sys
    ins=BattleKRInserter('input.gba','battle_dialogue.json')
    print(f"번역 사전: unique {len(ins.uni)}개 + 마징가 폴백")
    r=ins.build('srwj_battle_kr.gba')
    print(f"변경 블록: {r['changed']}/177, 번역 토큰: {r['tokens']}개")
    print(f"확장영역 0x{r['dest']:X}부터 0x{r['used']:X} 사용, ROM 0x{r['rom']:X}")
    print("저장: srwj_battle_kr.gba")
