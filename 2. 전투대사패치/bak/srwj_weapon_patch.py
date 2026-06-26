# -*- coding: utf-8 -*-
"""무기명 풀 한글 패치: in-place 우선, 길면 free space relocation + 포인터 전체 갱신"""
import json,struct,sys
from srwj_battle_kr_insert import BattleKRInserter
from _wpn_tr import TR

IN  = sys.argv[1] if len(sys.argv)>1 else 'srwj_battle_kr.gba'
OUT = sys.argv[2] if len(sys.argv)>2 else 'srwj_battle_kr.gba'
RELOC_BASE = 0x1340000   # 확장영역 내 미사용 구간

def main():
    ins=BattleKRInserter('all.gba','battle_dialogue_unique.json'); cx=ins.cx
    rom=bytearray(open(IN,'rb').read())
    real=json.load(open('_untrans_real.json',encoding='utf-8'))
    assert len(TR)==len(real), f"{len(TR)} != {len(real)}"
    # relocation 영역이 비어있는지 확인
    chunk=rom[RELOC_BASE:RELOC_BASE+0x400]
    if any(b!=0 and b!=0xFF for b in chunk):
        print(f"경고: 0x{RELOC_BASE:X} 비어있지 않음 (앞 16B: {chunk[:16].hex()})")
    ip=0; rc=0; fp=RELOC_BASE; reloc_log=[]
    for e,tr in zip(real,TR):
        off=int(e['off'],16)
        ol=0
        while rom[off+ol]!=0: ol+=1
        enc=cx.enc_text(ins.normalize(tr))
        if len(enc)<=ol:
            rom[off:off+len(enc)]=enc
            for i in range(off+len(enc), off+ol): rom[i]=0
            ip+=1
        else:
            # free space에 기록
            rom[fp:fp+len(enc)]=enc; rom[fp+len(enc)]=0
            old=struct.pack('<I',0x08000000+off)
            new=struct.pack('<I',0x08000000+fp)
            # ROM 전체에서 이 무기명을 가리키는 포인터 모두 갱신
            cnt=0; pos=0
            while True:
                pos=rom.find(old,pos)
                if pos<0: break
                rom[pos:pos+4]=new; pos+=4; cnt+=1
            reloc_log.append((tr,off,fp,cnt))
            fp+=len(enc)+1; fp=(fp+1)&~1
            rc+=1
    open(OUT,'wb').write(rom)
    print(f"in-place {ip}, relocation {rc} (포인터 갱신), free 0x{RELOC_BASE:X}~0x{fp:X}")
    print("--- relocation 상세 ---")
    for tr,off,nf,cnt in reloc_log:
        print(f"  {repr(tr)}: 0x{off:X}->0x{nf:X} (포인터 {cnt}곳 갱신)")

if __name__=='__main__': main()
