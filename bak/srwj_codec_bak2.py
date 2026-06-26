# -*- coding: utf-8 -*-
"""
srwj_codec.py — 슈퍼로봇대전 J 한글 대사 인코더

한글 텍스트를 게임이 이해하는 사전 압축 코드(바이트열)로 변환한다.

원리
----
한글 패치 ROM 의 폰트는 일본 한자 글리프 슬롯(亜~美, 2350자)에
한글 글자 이미지(가~힝, 2350자)를 덮어쓴 상태이다.
따라서 대사에 '한자'를 넣으면 화면에는 그 자리의 '한글'이 출력된다.

  한글 글자  →  대응 일본 한자  →  그 한자를 디코딩하는 사전 코드  →  바이트열

사전(코덱)이 직접 보유한 한자는 일부뿐이라, 사전에 없는 한자는
seg1(코드 0xC300~0xCA3A) 의 '거의 안 쓰이는 슬롯'을 희생시켜
해당 한자를 가리키도록 사전 테이블을 덮어쓴다.

코드 배정은 반드시 2패스로 한다.
  패스1: 사전에 이미 있는 글자들의 코드를 모두 확정 → '사용중 코드' 집합 구성
  패스2: 사전에 없는 글자에 희생슬롯 배정 (단, '사용중 코드'는 절대 건드리지 않음)
이렇게 해야 희생슬롯이 1화에서 실제로 쓰는 글자의 코드를 덮어쓰지 않는다.
"""

import json
import re
import srwj_decode as D

HANGUL_LO, HANGUL_HI = 0xAC00, 0xD7A3      # 가 ~ 힣
SEG1_LO, SEG1_HI = 0xC300, 0xCA3B          # seg1 코드 범위
DICT_SEG1_TBL = 0x266                      # seg1 SJIS 테이블의 헤더 기준 오프셋
DISPLAY_WIDTH = 25                         # 대사창 가로 최대 폭


# ──────────────────────────────────────────────────────────
#  ASCII → 전각(게임용) 문자 정규화 표
# ──────────────────────────────────────────────────────────
def _build_normalize():
    m = {
        ' ': '\u3000', '\xa0': '\u3000', '\u200b': '',
        '.': '。', ',': '、', '!': '！', '?': '？',
        '"': '”', "'": '’', '(': '（', ')': '）',
        '~': '～', ':': '：', ';': '；', '/': '／',
        '·': '・',
    }
    for i in range(10):                    # 0-9 → ０-９
        m[chr(0x30 + i)] = chr(0xFF10 + i)
    for i in range(26):                    # A-Z, a-z → 전각
        m[chr(0x41 + i)] = chr(0xFF21 + i)
        m[chr(0x61 + i)] = chr(0xFF41 + i)
    return m

NORMALIZE = _build_normalize()


def char_width(ch: str) -> int:
    """글자 화면 폭. 전각(한글·전각기호·전각영숫자·가나) = 2, 반각 = 1.

    normalize_text() 가 마침표·쉼표·느낌표·물음표·영문·숫자를 모두 전각으로
    바꾸고, '…' 을 '・・・' 로 펼치므로, 한글뿐 아니라 이 전각 문자들도
    화면에서 2칸을 차지한다. 한글만 2로 계산하면 실제 폭을 과소평가해
    첫 줄이 대사창을 넘쳐 통째로 안 나오는 문제가 생긴다.
    """
    o = ord(ch)
    # 한글 음절
    if HANGUL_LO <= o <= HANGUL_HI:
        return 2
    # 전각 ASCII (！？ＡＺ０９ 등 U+FF01~FF60) 및 전각기호(U+FFE0~FFE6)
    if 0xFF01 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6:
        return 2
    # CJK 구두점·기호 (。、・「」『』〜… 등 U+3000~U+303F)
    if 0x3000 <= o <= 0x303F:
        return 2
    # 히라가나·가타카나 (U+3040~U+30FF)
    if 0x3040 <= o <= 0x30FF:
        return 2
    # 한글 자모 (U+1100~U+11FF, U+3130~U+318F)
    if 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
        return 2
    # CJK 한자 (U+4E00~U+9FFF) — 폰트가 한글로 덮인 자리도 2칸
    if 0x4E00 <= o <= 0x9FFF:
        return 2
    # 그 외(반각 ASCII, 반각 가나 등)
    return 1


def text_width(s: str) -> int:
    return sum(char_width(c) for c in s)


_ELLIPSIS_RE = re.compile(r'[.\uFF0E]{2,}')   # 점 2개 이상 연속


def normalize_text(s: str) -> str:
    """대사 텍스트를 게임용 전각 문자로 정규화.

    - '…','‥' 및 마침표 2개 이상 연속 → 게임식 줄임표 '・' 반복
      (번역가가 "..." 로 쓴 줄임표가 "。。。" 가 되는 것을 방지)
    - 그 외 ASCII 기호/영숫자 → 전각
    """
    # 줄임표 전처리
    s = s.replace('…', '・・・').replace('‥', '・・')
    s = _ELLIPSIS_RE.sub(lambda m: '・' * len(m.group()), s)
    # 글자별 정규화
    return ''.join(NORMALIZE.get(ch, ch) for ch in s)


# ──────────────────────────────────────────────────────────
#  한글 코덱
# ──────────────────────────────────────────────────────────
class HangulCodec:
    """한글 → 게임 코드 변환기.

    사용 순서:
        codec = HangulCodec(rom_bytes, 'korea2350.txt', 'japan2350.txt',
                            'seg1_victim_rank.json')
        codec.plan(list_of_all_dialogue_texts)   # 코드 배정 + 사전패치 계획
        data = codec.encode_line('안녕하세요')    # 바이트열
        patches = codec.dict_patches             # 사전 덮어쓰기 목록
    """

    def __init__(self, rom: bytes, korea_txt: str, japan_txt: str,
                 victim_rank, expand_mode: bool = False):
        """victim_rank: seg1 희생슬롯 우선순위(JSON 경로 또는 코드 리스트).
        expand_mode: True 이면 사전에 없는 글자를 희생슬롯이 아니라
                     seg1 을 물리적으로 늘려 만든 '새 코드'(0xCA3B~)에 배정.
        """
        self.rom = rom
        self.dic = D.Dictionary(rom)
        self.HDR = D.DICT_HDR
        self.expand_mode = expand_mode
        self._expansion_ptr = 0       # 확장 코드 배정 카운터

        # 1) 사전이 디코딩하는 '단일 글자 → 코드' 역맵
        self.char2code = {}
        for seg in self.dic._segs:
            lo, hi, off, el, kind = seg
            for code in range(lo, hi):
                if 0xC2 < code < 0xC300:        # 무효 토큰 구간
                    continue
                s = self.dic.decode(code)
                if len(s) == 1 and s not in self.char2code:
                    self.char2code[s] = code

        # 2) 한글 ↔ 한자 폰트 매핑 로드
        ko = open(korea_txt, encoding='utf-8').read()
        ko = ko.replace('\r', '').replace('\n', '').strip()
        jp_lines = [l.strip() for l in
                    open(japan_txt, encoding='utf-16').read().split('\n')
                    if l.strip()]
        if len(ko) != len(jp_lines):
            raise ValueError(f'매핑 개수 불일치: 한글 {len(ko)} / 한자 {len(jp_lines)}')
        self.ko2kanji = {ko[i]: jp_lines[i].split('=')[1]
                         for i in range(len(ko))}

        # 3) seg1 희생슬롯 후보 (사용량 적은 순으로 정렬된 코드 목록)
        if isinstance(victim_rank, str):
            self.victim_rank = json.load(open(victim_rank, encoding='utf-8'))
        else:
            self.victim_rank = list(victim_rank)

        # 상태
        self._resolved = {}           # 정규화문자 → 코드
        self._used_codes = set()      # 이미 쓰는(건드리면 안 되는) 코드
        self._dict_patches = {}       # rom_offset → 2바이트
        self._victim_ptr = 0
        self.unresolved = set()       # 끝내 코드를 못 구한 문자

    # ──────────────────────────────────────────────
    def _target_char(self, ch: str):
        """정규화된 문자가 화면에 나오게 하려면 사전이 디코딩해야 할 '대상 글자'.

        한글  → 대응 일본 한자
        그 외 → 자기 자신
        """
        if HANGUL_LO <= ord(ch) <= HANGUL_HI:
            return self.ko2kanji.get(ch)        # 매핑에 없으면 None
        return ch

    def _alloc_victim(self, target_char: str):
        """희생 seg1 슬롯 하나를 받아 target_char 를 가리키도록 패치 등록.

        '사용중 코드'(_used_codes)는 절대 고르지 않는다.
        Returns: 배정된 seg1 코드, 실패 시 None
        """
        try:
            sjis = target_char.encode('cp932')
        except UnicodeEncodeError:
            return None
        if len(sjis) != 2:
            return None
        while self._victim_ptr < len(self.victim_rank):
            code = self.victim_rank[self._victim_ptr]
            self._victim_ptr += 1
            if code in self._used_codes:        # 1화가 쓰는 코드 → 보호
                continue
            off = self.HDR + DICT_SEG1_TBL + (code - SEG1_LO) * 2
            if off in self._dict_patches:
                continue
            self._dict_patches[off] = sjis
            self._used_codes.add(code)
            return code
        return None      # 희생슬롯 고갈

    def _alloc_expansion(self, target_char: str):
        """확장 모드: seg1 을 늘려 만든 새 코드(0xCA3B~)를 배정."""
        try:
            sjis = target_char.encode('cp932')
        except UnicodeEncodeError:
            return None
        if len(sjis) != 2:
            return None
        code = SEG1_HI + self._expansion_ptr      # 0xCA3B 부터
        self._expansion_ptr += 1
        off = self.HDR + DICT_SEG1_TBL + (code - SEG1_LO) * 2
        self._dict_patches[off] = sjis
        self._used_codes.add(code)
        return code

    def _alloc_slot(self, target_char: str):
        """확장 모드면 새 코드, 아니면 희생슬롯 배정."""
        if self.expand_mode:
            return self._alloc_expansion(target_char)
        return self._alloc_victim(target_char)

    @property
    def n_expansion(self):
        """확장 모드에서 새로 늘린 seg1 코드 개수."""
        return self._expansion_ptr

    # ──────────────────────────────────────────────
    def plan(self, texts):
        """여러 대사 텍스트의 모든 문자에 코드를 2패스로 배정한다."""
        chars = set()
        for t in texts:
            for ch in normalize_text(t):
                if ch not in ('\n', '\r', ''):
                    chars.add(ch)

        # ── 패스 1: 사전에 이미 있는 글자 확정 ──
        missing = []        # (정규화문자, 대상글자)
        for ch in sorted(chars):
            target = self._target_char(ch)
            if target is None:
                self.unresolved.add(ch)
                self._resolved[ch] = None
            elif target in self.char2code:
                code = self.char2code[target]
                self._resolved[ch] = code
                self._used_codes.add(code)
            else:
                missing.append((ch, target))

        # ── 패스 2: 사전에 없는 글자에 희생슬롯 배정 ──
        for ch, target in sorted(missing):
            code = self._alloc_slot(target)
            if code is None:
                self.unresolved.add(ch)
            self._resolved[ch] = code

    # ──────────────────────────────────────────────
    @staticmethod
    def code_to_bytes(code: int) -> bytes:
        """코드 → 토큰 바이트열 (1바이트 또는 2바이트 빅엔디안)."""
        if code <= 0xC2:
            return bytes([code])
        return bytes([(code >> 8) & 0xFF, code & 0xFF])

    def encode_line(self, text: str) -> bytes:
        """한 줄의 한글 텍스트를 사전코드 바이트열로 인코딩.

        plan() 이 먼저 실행되어 있어야 한다.
        해결 불가 문자는 건너뛴다(unresolved 에 기록).
        """
        out = bytearray()
        for ch in normalize_text(text):
            if ch in ('\n', '\r', ''):
                continue
            code = self._resolved.get(ch)
            if code is None and ch not in self._resolved:
                code = self._lazy_resolve(ch)
            if code is None:
                continue
            out += self.code_to_bytes(code)
        return bytes(out)

    def _lazy_resolve(self, ch: str):
        """plan() 에서 누락된 문자를 뒤늦게 배정(안전망)."""
        target = self._target_char(ch)
        if target is None:
            self.unresolved.add(ch)
            self._resolved[ch] = None
            return None
        if target in self.char2code:
            code = self.char2code[target]
        else:
            code = self._alloc_slot(target)
        if code is None:
            self.unresolved.add(ch)
        else:
            self._used_codes.add(code)
        self._resolved[ch] = code
        return code

    # ──────────────────────────────────────────────
    @property
    def dict_patches(self):
        """사전 덮어쓰기 목록: [(rom_offset, 2바이트), ...]"""
        return sorted(self._dict_patches.items())

    @property
    def victim_count(self):
        return len(self._dict_patches)

    def report(self):
        """배정 결과 요약 문자열."""
        n_hangul = sum(1 for c, v in self._resolved.items()
                       if v is not None and HANGUL_LO <= ord(c) <= HANGUL_HI)
        lines = [f'  배정한 문자 종류 : {len(self._resolved)} (한글 {n_hangul})']
        if self.expand_mode:
            lines.append(f'  사전 확장 새 코드: {self.n_expansion}')
        else:
            lines.append(f'  희생 seg1 슬롯   : {self.victim_count} '
                         f'/ 가용 {len(self.victim_rank)}')
        if self.unresolved:
            lines.append(f'  ★ 코드 미배정 문자 {len(self.unresolved)}개: '
                         + ''.join(sorted(self.unresolved)))
        return '\n'.join(lines)
