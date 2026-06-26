# -*- coding: utf-8 -*-
"""
srwj_wrap.py — 대사 줄바꿈 / 대사창 폭 맞춤

규칙
----
* 대사창 가로 최대 폭 = 25 (한글 2, 그 외 1)
* 한 턴의 첫 줄은 화면에 "화자「" 가 먼저 붙으므로 그만큼 폭이 줄어든다.
* 줄 수는 일본어 원본 턴의 줄 수에 맞추는 것을 기본으로 한다.
  단, 한국어가 그 줄 수에 도저히 안 들어가면 자동으로 줄을 늘리고 경고한다.
"""

from srwj_codec import normalize_text, text_width, char_width, DISPLAY_WIDTH

# 화자 이름이 차지할 수 있는 최대 폭 (한글 6자 = 12) + 여는 「(폭 2) = 14
MAX_SPEAKER_RESERVE = 14
# 닫는 」(폭 2) 가 마지막 줄 끝에 붙으므로 마지막 줄은 그만큼 덜 채운다
CLOSE_BRACKET_RESERVE = 2
# 단어 사이 구분자: 전각 공백(게임에서 폭 2). normalize_text 가 일반 공백을
# 전각 공백으로 바꾸므로, 폭 계산도 반드시 전각폭(2)으로 해야 한다.
SEP = '\u3000'
SEP_W = char_width(SEP)        # = 2


def _hard_break(word: str, budget: int):
    """한 단어가 budget 보다 길면 폭 단위로 잘라 여러 조각으로."""
    pieces, cur, cw = [], '', 0
    for ch in word:
        w = char_width(ch)
        if cur and cw + w > budget:
            pieces.append(cur)
            cur, cw = '', 0
        cur += ch
        cw += w
    if cur:
        pieces.append(cur)
    return pieces


def greedy_wrap(text: str, budgets, default_budget: int):
    """text 를 폭 제한에 맞춰 그리디 줄바꿈.

    Args:
        text          : 정규화된 텍스트(공백은 전각 '　')
        budgets       : 앞쪽 줄들의 폭 예산 리스트
        default_budget: budgets 를 다 쓴 뒤 적용할 폭 예산

    Returns: 줄 문자열 리스트
    """
    def budget_of(i):
        return budgets[i] if i < len(budgets) else default_budget

    words = [w for w in text.split('\u3000')]      # 전각 공백 기준 분리
    lines, cur, cw = [], '', 0
    li = 0

    for word in words:
        if word == '':
            continue
        ww = text_width(word)
        bud = budget_of(li)

        # 단어 자체가 한 줄보다 길면 강제 분할
        if ww > bud:
            if cur:
                lines.append(cur)
                li += 1
                cur, cw = '', 0
                bud = budget_of(li)
            for piece in _hard_break(word, bud):
                lines.append(piece)
                li += 1
                bud = budget_of(li)
            continue

        add = ww + (SEP_W if cur else 0)        # 단어 사이 전각 공백(폭 2)
        if cur and cw + add > bud:
            lines.append(cur)
            li += 1
            cur, cw = word, ww
        else:
            if cur:
                cur += SEP + word
                cw += add
            else:
                cur, cw = word, ww

    if cur:
        lines.append(cur)
    return lines if lines else ['']


def speaker_reserve(speaker) -> int:
    """화자 이름이 첫 줄에서 차지하는 폭(= 이름폭 + 여는 「).

    speaker 가 None  → 화자를 모름 → 안전하게 최대치(14)
    speaker 가 ''    → 화자 없음(독백) → 여는 괄호 폭만(2)
    speaker 가 이름  → text_width(이름) + 「(2), 단 최대 14로 제한
    """
    if speaker is None:
        return MAX_SPEAKER_RESERVE
    name = normalize_text(str(speaker).strip())
    if not name:
        return CLOSE_BRACKET_RESERVE          # 독백: 여는 괄호만
    r = text_width(name) + 2                   # 이름 + 「(폭 2)
    return min(r, MAX_SPEAKER_RESERVE)


def fit_turn_lines(kr_text: str, jp_line_count: int,
                   first_line_reserve: int = MAX_SPEAKER_RESERVE,
                   speaker=None):
    """한 턴의 한국어 텍스트를 게임용 줄 목록으로 변환.

    화면 폭(25) 안에 들어가도록 줄바꿈한다. 특히:
      * 첫 줄은 게임이 "화자「" 를 앞에 붙이므로 그만큼(speaker 폭) 덜 채운다.
        speaker 인자가 주어지면 그 이름 폭으로 자동 계산, 없으면
        first_line_reserve(기본 14 = 최대 화자폭) 를 쓴다.
      * 마지막 줄은 게임이 끝에 "」" 를 붙이므로 2칸 덜 채운다.
    → 첫 줄/끝 줄이 대사창을 넘쳐 통째로 사라지는 문제를 막는다.

    Args:
        kr_text            : 번역 한국어 (줄바꿈 \\n 포함 가능)
        jp_line_count      : 일본어 원본 턴의 줄 수 (목표)
        first_line_reserve : speaker 가 None 일 때 첫 줄에서 뺄 폭
        speaker            : 화자 이름(번역). 주어지면 첫 줄 reserve 자동 계산.

    Returns:
        (lines, warnings)
    """
    warnings = []
    norm = normalize_text(kr_text)

    # 첫 줄 reserve: speaker 가 주어지면 그것으로, 아니면 인자값
    if speaker is not None:
        reserve = speaker_reserve(speaker)
    else:
        reserve = first_line_reserve
    first_budget = max(4, DISPLAY_WIDTH - reserve)
    last_budget  = max(4, DISPLAY_WIDTH - CLOSE_BRACKET_RESERVE)

    # 번역가의 \n 줄
    raw_lines = [ln for ln in norm.split('\n')]
    # 끝쪽 빈 줄 제거
    while raw_lines and raw_lines[-1].strip('\u3000') == '':
        raw_lines.pop()
    if not raw_lines:
        raw_lines = ['']

    def line_budget(idx, total):
        """idx 번째 줄(전체 total 줄)의 폭 예산."""
        b = DISPLAY_WIDTH
        if idx == 0:
            b = min(b, first_budget)
        if idx == total - 1:
            b = min(b, last_budget)
        return b

    def line_ok(idx, s, total):
        return text_width(s.strip('\u3000')) <= line_budget(idx, total)

    # (A) 번역가 줄 수가 목표와 같고 폭(첫·끝 reserve 포함)도 OK → 그대로 사용
    if len(raw_lines) == jp_line_count and \
            all(line_ok(i, s, len(raw_lines)) for i, s in enumerate(raw_lines)):
        return [s.strip('\u3000') for s in raw_lines], warnings

    # (B) 재배치: 전체 텍스트를 목표 줄 수에 맞춰 그리디 줄바꿈
    joined = '\u3000'.join(s.strip('\u3000') for s in raw_lines
                           if s.strip('\u3000') != '')
    budgets = [first_budget] + [DISPLAY_WIDTH] * max(0, jp_line_count - 1)
    lines = greedy_wrap(joined, budgets, DISPLAY_WIDTH)

    # 마지막 줄이 닫는 」 까지 포함해 넘치면, 넘치는 부분을 새 줄로 분리
    lines = _enforce_last_line(lines, last_budget)

    if len(lines) > jp_line_count:
        warnings.append(
            f'줄 수 초과: 목표 {jp_line_count}줄 → 실제 {len(lines)}줄 '
            f'(한국어가 대사창에 다 안 들어감)')
    elif len(lines) < jp_line_count:
        lines = lines + [''] * (jp_line_count - len(lines))

    # 최종 폭 점검 (첫 줄·끝 줄 reserve 반영)
    total = len(lines)
    for i, s in enumerate(lines):
        bud = line_budget(i, total)
        w = text_width(s)
        if w > bud:
            warnings.append(f'{i+1}번째 줄 폭 초과: {w} > {bud}  "{s}"')

    return lines, warnings


def _enforce_last_line(lines, last_budget):
    """마지막 줄이 last_budget 을 넘으면 뒤쪽 단어를 새 줄로 내린다."""
    if not lines:
        return lines
    last = lines[-1]
    if text_width(last) <= last_budget:
        return lines
    # 전각 공백 기준으로 단어 분해 후, last_budget 에 맞게 재배치
    words = [w for w in last.split('\u3000') if w != '']
    head, cur, cw = [], '', 0
    for word in words:
        ww = text_width(word)
        add = ww + (SEP_W if cur else 0)
        if cur and cw + add > last_budget:
            head.append(cur)
            cur, cw = word, ww
        else:
            if cur:
                cur += SEP + word
                cw += add
            else:
                cur, cw = word, ww
    if cur:
        head.append(cur)
    return lines[:-1] + head
