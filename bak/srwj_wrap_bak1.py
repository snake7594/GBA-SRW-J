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

        add = ww + (1 if cur else 0)            # 단어 사이 공백 1
        if cur and cw + add > bud:
            lines.append(cur)
            li += 1
            cur, cw = word, ww
        else:
            if cur:
                cur += '\u3000' + word
                cw += add
            else:
                cur, cw = word, ww

    if cur:
        lines.append(cur)
    return lines if lines else ['']


def fit_turn_lines(kr_text: str, jp_line_count: int,
                   first_line_reserve: int = 15):
    """한 턴의 한국어 텍스트를 게임용 줄 목록으로 변환.

    Args:
        kr_text            : 번역 한국어 (줄바꿈 \\n 포함 가능)
        jp_line_count      : 일본어 원본 턴의 줄 수 (목표)
        first_line_reserve : 첫 줄에서 "화자「" 가 차지하는 폭

    Returns:
        (lines, warnings)
          lines    : 줄 문자열 리스트 (정규화 완료, 길이 >= 1)
          warnings : 경고 메시지 리스트
    """
    warnings = []
    norm = normalize_text(kr_text)
    first_budget = max(4, DISPLAY_WIDTH - first_line_reserve)

    # 번역가의 \n 줄
    raw_lines = [ln for ln in norm.split('\n')]
    raw_lines = [ln for ln in raw_lines]            # 빈 줄도 유지
    # 끝쪽 빈 줄 제거
    while raw_lines and raw_lines[-1].strip('\u3000') == '':
        raw_lines.pop()
    if not raw_lines:
        raw_lines = ['']

    def line_ok(idx, s):
        bud = first_budget if idx == 0 else DISPLAY_WIDTH
        return text_width(s.strip('\u3000')) <= bud

    # (A) 번역가 줄 수가 목표와 같고 폭도 OK → 그대로 사용
    if len(raw_lines) == jp_line_count and \
            all(line_ok(i, s) for i, s in enumerate(raw_lines)):
        return [s.strip('\u3000') for s in raw_lines], warnings

    # (B) 재배치: 전체 텍스트를 목표 줄 수에 맞춰 그리디 줄바꿈
    joined = '\u3000'.join(s.strip('\u3000') for s in raw_lines
                           if s.strip('\u3000') != '')
    budgets = [first_budget] + [DISPLAY_WIDTH] * max(0, jp_line_count - 1)
    lines = greedy_wrap(joined, budgets, DISPLAY_WIDTH)

    if len(lines) > jp_line_count:
        warnings.append(
            f'줄 수 초과: 목표 {jp_line_count}줄 → 실제 {len(lines)}줄 '
            f'(한국어가 대사창에 다 안 들어감)')
    elif len(lines) < jp_line_count:
        # 부족하면 끝에 빈 줄 채워 줄 수 맞춤
        lines = lines + [''] * (jp_line_count - len(lines))

    # 폭 초과 점검
    for i, s in enumerate(lines):
        bud = first_budget if i == 0 else DISPLAY_WIDTH
        w = text_width(s)
        if w > bud:
            warnings.append(f'{i+1}번째 줄 폭 초과: {w} > {bud}  "{s}"')

    return lines, warnings
