# -*- coding: utf-8 -*-
"""슈퍼로봇대전 J 한글 패치 코덱 (인코딩 / 디코딩 / 길이맞춤).

폰트 맵핑 원리
    한글 폰트 패치는 JIS 제1수준 한자 글리프 자리에 한글 2350자를 채워 넣었다.
    따라서 한글 음절을 ROM에 적으려면, 그 한글과 같은 ku/ten 격자에 있는 한자의
    Shift-JIS(cp932) 코드를 적으면 된다.
        한글 → EUC-KR 2바이트 → 같은 바이트를 EUC-JP로 해석 = 한자 → 그 한자의 cp932 코드
        예) 가(EUC-KR B0A1) → EUC-JP B0A1 = 亜 → cp932 889F

인코딩 규칙
    한글 음절            → 폰트맵 SJIS 2바이트
    전각 영숫자/기호/공백 → 그 문자의 cp932 2바이트 그대로 (원문 보존: ０-９ Ａ-Ｚ 「」、。・－～　 등)
    반각 ASCII(0x20-7E)  → 1바이트 그대로 (제어/포맷 시퀀스: #| %s %-d &G 등)
    제어코드(0x00-0x1F)   → 1바이트 그대로

공백 처리
    번역(JSON)에서는 읽기 쉬운 일반 공백(0x20)을 쓰고, 인코딩 시 전각 공백(　,8140)으로
    자동 변환한다. 게임 표시는 전각 폭이 맞다.
"""

# 일반 공백 → 전각 공백, 가운뎃점 변형 → 전각 가운뎃점 통일
_NORMALIZE = {
    ' ': '\u3000',     # 반각 공백 → 전각 공백
    '·': '\u30FB',     # 가운뎃점(U+00B7) → 전각 가운뎃점(・)
    '•': '\u30FB',
}


def normalize(text):
    """번역 문자열을 ROM 기록용으로 정규화 (공백/가운뎃점)."""
    return ''.join(_NORMALIZE.get(c, c) for c in text)


def _kor_to_sjis(syllable):
    """한글 음절 1자 → SJIS 2바이트. KS X 1001 미수록이면 None."""
    try:
        euc = syllable.encode('euc-kr')
    except UnicodeEncodeError:
        return None
    if len(euc) != 2:
        return None
    b0, b1 = euc[0], euc[1]
    if not (0xB0 <= b0 <= 0xC8 and 0xA1 <= b1 <= 0xFE):   # 폰트가 보유한 한글 영역
        return None
    try:
        return euc.decode('euc-jp').encode('cp932')        # 같은 격자 한자의 cp932 코드
    except Exception:
        return None


def _char_to_bytes(ch):
    """문자 1개 → (bytes, kind). kind: kor/fullwidth/half/ctrl/BAD."""
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3:                  # 한글 음절
        b = _kor_to_sjis(ch)
        return (b, 'kor') if b else (None, 'BAD')
    if o < 0x20:                                # 제어코드
        return (bytes([o]), 'ctrl')
    if 0x20 <= o <= 0x7E:                       # 반각 ASCII (포맷/제어 시퀀스)
        return (bytes([o]), 'half')
    try:                                        # 전각/기타 → cp932 그대로
        return (ch.encode('cp932'), 'fullwidth')
    except Exception:
        return (None, 'BAD')


def encode(text):
    """번역 문자열 → (bytes, bad_chars). 정규화(공백 등) 후 인코딩."""
    text = normalize(text)
    out = bytearray(); bad = []
    for ch in text:
        b, kind = _char_to_bytes(ch)
        if b is None:
            bad.append(ch)
        else:
            out += b
    return bytes(out), bad


def fit_length(text, maxlen):
    """전각 공백을 오른쪽부터 줄여 maxlen 바이트 이내로 맞춘다 (반각은 만들지 않음).
    공백을 다 빼도 넘치면 그대로 반환(상위에서 재배치 처리)."""
    if len(encode(text)[0]) <= maxlen:
        return text
    chars = list(normalize(text))
    while len(encode(''.join(chars))[0]) > maxlen:
        spaces = [i for i, c in enumerate(chars) if c == '\u3000']
        if not spaces:
            break
        chars.pop(spaces[-1])
    return ''.join(chars)


# ---- 디코딩 (검증/표시용) ----

def _sjis_to_kor(b2):
    """한글영역 SJIS 2바이트 → 한글 음절 (아니면 None)."""
    try:
        return b2.decode('shift_jis').encode('euc-jp').decode('euc-kr')
    except Exception:
        return None


def decode(b, stop_at_null=True):
    """바이트열 → 사람이 읽는 문자열 (한글영역=한글, 전각=원문기호).
    stop_at_null=True 면 첫 0x00에서 멈춘다."""
    s = []; i = 0
    while i < len(b):
        c = b[i]
        if c == 0x00:
            if stop_at_null:
                break
            s.append('\u25AF'); i += 1; continue
        if c >= 0x88 and i + 1 < len(b):
            k = _sjis_to_kor(b[i:i+2])
            if k and '\uAC00' <= k <= '\uD7A3':
                s.append(k); i += 2; continue
        if c >= 0x81 and i + 1 < len(b):
            try:
                s.append(b[i:i+2].decode('cp932'))
            except Exception:
                s.append('?')
            i += 2
        elif 0x20 <= c <= 0x7E:
            s.append(chr(c)); i += 1
        else:
            s.append(f'<{c:02x}>'); i += 1
    return ''.join(s)


def has_kana(b):
    """SJIS 카타카나(0x8340-0x8396)/히라가나(0x829F-0x82F1)/장음(815B)이 남아있으면 True."""
    i = 0
    while i < len(b) - 1:
        c = b[i]
        if c == 0x00:
            break
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            code = (c << 8) | b[i+1]
            if 0x829F <= code <= 0x82F1 or 0x8340 <= code <= 0x8396 or code == 0x815B:
                return True
            i += 2
        else:
            i += 1
    return False
