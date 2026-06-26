#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"ko" 필드 띄어쓰기 제거 스크립트.

각 줄이  "ko": "..."  형태일 때, 따옴표 안 내용의 모든 공백
(반각 스페이스 U+0020, 전각 스페이스 U+3000)을 제거한다.
off / len / jp 등 다른 줄과 들여쓰기·따옴표·콤마 등 형식은 100% 그대로 둔다.

사용법:
    python remove_ko_spaces.py 입력파일 [출력파일]
출력파일을 생략하면 입력파일을 덮어쓴다.
"""
import re
import sys

# 줄 전체를  (앞부분)(값)(뒷부분)  으로 분리.
#  앞부분 = 들여쓰기 + "ko": "
#  값     = 따옴표 안 내용 (그리디로 마지막 " 직전까지)
#  뒷부분 = 닫는 따옴표 + 선택적 콤마 + 줄바꿈/공백
KO_RE = re.compile(r'^(\s*"ko"\s*:\s*")(.*)("(?:\s*,)?\s*)$')


def strip_spaces(value: str) -> str:
    return value.replace(' ', '').replace('\u3000', '')


def process_lines(lines):
    out, changed = [], 0
    for line in lines:
        m = KO_RE.match(line)
        if m:
            pre, val, post = m.group(1), m.group(2), m.group(3)
            new_val = strip_spaces(val)
            if new_val != val:
                changed += 1
            out.append(pre + new_val + post)
        else:
            out.append(line)
    return out, changed


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    inp = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else inp
    with open(inp, encoding='utf-8') as f:
        lines = f.readlines()
    new_lines, changed = process_lines(lines)
    with open(outp, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"완료: ko 줄 {changed}개에서 띄어쓰기 제거 -> {outp}")


if __name__ == '__main__':
    main()
