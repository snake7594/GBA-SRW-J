# 슈퍼로봇대전 J 한글화 프로젝트 (TRANS‑SRWJ)

GBA 『슈퍼로봇대전 J』(Super Robot Taisen J, 2005)의 **게임 전반을 한국어화**하는 PC용 파이썬 툴킷과 번역 데이터 모음입니다.
한글 폰트 이식부터 타이틀·이미지, 시나리오 대사, 전투 대사, 메뉴/시스템 텍스트까지 게임 내 텍스트·그래픽을 단계별로 한국어로 교체합니다.

최종 결과물은 **원본 ROM을 포함하지 않는 `xdelta` 차분 패치**로 배포됩니다.

> ⚠️ **법적 고지 — ROM 미포함**
> 이 저장소에는 게임 ROM이 **포함되어 있지 않으며, 절대 커밋하지 마세요.**
> 원본 일본판 ROM과 패치된 ROM은 저작권 보호 대상입니다. 배포물은 ROM 데이터를 담지 않는
> `xdelta` **차분 패치**뿐입니다. 본인이 **합법적으로 소유한** 일본판 ROM에 직접 적용해 사용하세요.
> `.gitignore` 가 `*.gba`·세이브·이미지 등을 자동 제외합니다. (단, `*.xdelta` 차분 패치는 ROM을 포함하지 않으므로 추적합니다.)

---

## 빠른 시작 — 패치 적용 (플레이어용)

1. **합법적으로 소유한** 일본판 원본 ROM `Super Robot Taisen J (Japan).gba` (16MB) 를 준비합니다.
2. [**Releases**](https://github.com/snake7594/TRANS-SRWJ/releases/latest) 에서 최신 `.xdelta` 패치를 내려받습니다.
3. [xdelta](https://github.com/jmacd/xdelta) 로 적용합니다(또는 xdelta UI 도구 사용):

   ```bash
   xdelta -d -s "Super Robot Taisen J (Japan).gba" "Super.Robot.Taisen.J.Korean._20260625.xdelta" "srwj_korean.gba"
   ```

4. 생성된 `srwj_korean.gba` (한글 적용, 자동 확장으로 32MB) 를 mGBA·VBA 등 에뮬레이터나 플래시카트에서 실행합니다.

> 배포용 `.xdelta` 패치는 저장소 트리가 아니라 **[Releases](https://github.com/snake7594/TRANS-SRWJ/releases)** 에 올라갑니다.

---

## 저장소 구성

| 폴더 / 파일 | 내용 |
|---|---|
| [`1. 폰트변경/`](1.%20폰트변경/) | 한자 글리프 자리에 한글 2350자(KS X 1001)를 비트맵으로 채우는 **폰트 이식** 도구 |
| [`4. 이미지/`](4.%20이미지/) | 타이틀 로고·에피소드 제목·전투 메시지·저작권 화면·UI 아이콘 등 **그래픽 한글화** 도구 |
| [`0. 시나리오/`](0.%20시나리오/) | 전 70챕터 **시나리오 대사** 삽입 도구 + 번역 매칭 엑셀(`srwj_matched_all_*.xlsx`) |
| [`2. 전투대사패치/`](2.%20전투대사패치/) | **전투(배틀) 대사·합체기** 삽입 도구 + `battle_dialogue*.json` |
| [`3. SJIS추출/`](3.%20SJIS추출/) | **메뉴·정신커맨드·아이템 등 시스템 텍스트** 추출·번역(`translations.json`)·빌드 |
| 루트 `!xdelta_e_SRWJ.bat` | 최종 통합 ROM에서 **배포용 차분 패치(xdelta)** 를 만드는 스크립트 (패치 자체는 [Releases](https://github.com/snake7594/TRANS-SRWJ/releases)) |

각 폴더에는 자체 `README` 가 들어 있습니다.

---

## 한글화 파이프라인

각 단계는 앞 단계 결과 ROM을 입력으로 받아 누적 적용합니다.

```
원본 일본판 ROM (16MB)
   │
   ▼  1. 폰트변경      한자 글리프 → 한글 2350자 (물마루 Mulmaru 폰트)
   ▼  4. 이미지        타이틀/에피소드 제목/전투 메시지/저작권/UI 그래픽 한글화
   ▼  0. 시나리오      전 70챕터 대사 삽입 (ROM 16→32MB 자동 확장)
   ▼  2. 전투대사패치  전투 대사·합체기 삽입 (32MB ROM 필요)
   ▼  3. SJIS추출      메뉴/용어 등 시스템 텍스트 삽입
   │
   ▼  통합 한글 ROM (32MB)  ──[ xdelta ]──►  배포용 *.xdelta 차분 패치
```

> **핵심 원리 — 한글 = 한자 자리 바꿔치기**
> 폰트 단계에서 일본 한자 글리프(2350자) 자리에 한글(`가`~`힣`)을 덮어씁니다. 이후 텍스트에 한글을
> 적을 때는 같은 격자에 있던 한자의 Shift‑JIS 코드를 적습니다 (한글 → EUC‑KR → 같은 바이트를
> EUC‑JP로 해석 = 한자 → 그 한자의 cp932 코드). 한글 대사는 원문보다 길어 원래 자리에 안 들어가므로,
> 빈 공간에 블록을 새로 기록하고 포인터를 갱신하며, 모자라면 ROM을 32MB까지 자동 확장합니다.

---

## 단계별 상세

### 1. 폰트변경 — 한글 폰트 이식
한자 폰트 슬롯(SJIS `0x889F`~)에 한글 2350자를 16×11 비트맵으로 렌더링해 채웁니다. 반각 가타카나는
폭 압축(max‑pool)으로 처리합니다.
- `fill_hangul_galmuri.py` — 2350자 일괄 채우기. 예: `python fill_hangul_galmuri.py in.gba out.gba --font Mulmaru.ttf --size 12 --ox 1 --oy 0`
- `patch_glyph.py` — 개별 글리프 교체(예: `ド→도`), 반각 자동 압축, `--preview` ASCII 미리보기
- 폰트는 **물마루(Mulmaru)** 를 사용합니다. (폰트 파일은 라이선스상 저장소에 미포함 — 별도 준비)

### 4. 이미지 — 그래픽 한글화
ECD(LZSS) 압축 아카이브(약 15,000개 에셋)를 풀고 한글 이미지를 다시 넣습니다.
- `apply_all.py` — 타이틀 로고 + 에피소드 제목 68개 + 전투 메시지 70종 + 저작권 화면 + UI 아이콘 일괄 적용
- `make_titles.py` / `scn_title_insert.py` / `scn_title_extract.py` — 에피소드 제목 PNG 렌더·삽입·추출(SCR 타일맵 재생성·타일 중복 제거)
- `img_replace.py` · `bm_extract.py` · `credits_make.py` — 일반 이미지 교체 / 팔레트 보정 추출 / 저작권 화면 생성
- 데이터: `titles_ko.txt`(제목표), `credits_ko.txt`(저작권 문구), `pal_override.json`(팔레트 보정)

### 0. 시나리오 — 스토리 대사
전 70챕터 대사를 번역 매칭 엑셀에서 읽어 ROM에 삽입합니다. 모자라면 ROM을 자동 확장합니다.
- `patch_all.py` — 메인 패처. 예: `python patch_all.py --xlsx srwj_matched_all.xlsx --expand-dict --rom "Super Robot Taisen J (Japan).gba" --out srwj_korean_all_s.gba`
  - 옵션: `--reserve N`(화자「 예약 폭, 기본 7) · `--keep-jp`(미번역 턴은 일본어 유지) · `--placeholder-text "..."` · `--addr 0x...`
- `srwj_codec.py`(인코딩) · `srwj_wrap.py`(줄바꿈: 한 줄 14자, 첫 줄 7자) · `srwj_decode.py` · `srwj_parser.py` · `srwj_inject_lib.py` · `merge_xlsx.py`
- 데이터: **`srwj_matched_all_*.xlsx`** (번역 단일 원본 — `J열`(한국어)만 수정), `korea2350.txt`/`japan2350.txt`(폰트 매핑), `seg1_victim_rank.json`

### 2. 전투대사패치 — 전투/합체기 대사
JSON 기반으로 전투 대사를 삽입합니다. 합체기 블록(blk193)은 **바이트 길이를 보존하는 제자리 패치**로
화자/연출 동기화 깨짐(이른바 도몬 버그)을 방지합니다.
- `패치하기.py` — 메인 런처: `python 패치하기.py [input.gba] [output.gba]`
- `build_battle_json.py`(추출) · `srwj_battle_kr_insert.py`(삽입 엔진) · `rewrap_battle.py`(줄바꿈) · `verify_battle.py`(검증) · `srwj_battle_codec.py`(코덱)
- 데이터: `battle_dialogue.json` / `battle_dialogue_unique.json`(`ko`만 수정), `battle_dialogue_glossary.json`(용어 일관성 적용본)
- 입력 ROM은 폰트·타이틀·시나리오가 적용된 **32MB** 여야 합니다.

### 3. SJIS추출 — 메뉴/용어/시스템 텍스트
메뉴·정신커맨드·아이템 설명 등 SJIS 문자열을 추출·번역해 패치합니다. 슬롯에 맞으면 제자리, 넘치면
빈 공간으로 재배치하고 포인터를 갱신합니다.
- `build_patch.py` — `translations.json` → 패치 ROM(`output/슈퍼로봇대전J_한글.gba`) + `build_report.json`
- `srwj_codec.py`(코덱) · `verify.py`(검증: 미완성 카나/장음 잔존 탐지) · `remove_ko_spaces.py`(공백 정리)
- 데이터: **`translations.json`** (용어사전 겸 시스템 텍스트, 3267항목 — `ko`만 수정)

### 루트 / 빌드 — 배포 패치 생성
- `!xdelta_e_SRWJ.bat` — 통합 한글 ROM에서 `xdelta` 차분 패치를 생성:
  `xdelta -B 16777216 -e -9 -S djw -vfs "Super Robot Taisen J (Japan).gba" "srwj_korean_all.gba" "..._YYYYMMDD.xdelta"`
- 생성된 `.xdelta` 패치는 저장소 트리가 아닌 **[Releases](https://github.com/snake7594/TRANS-SRWJ/releases)** 로 배포합니다(원본 ROM 미포함 차분).

---

## 요구 환경
- **Python 3.8+** (Windows / macOS / Linux)
- `openpyxl` — 시나리오 단계의 번역 엑셀(.xlsx) 읽기
- `Pillow` — 폰트·이미지 렌더링 단계
- `xdelta` — 배포 패치 생성/적용 (Windows `xdelta.exe` 동봉 안 함, 각자 준비)

```bash
pip install openpyxl pillow
```

---

## 번역 수정 방법 (번역가용)
직접 ROM을 만지지 않고 **데이터 파일의 한국어만** 고치면 됩니다.
- 시나리오: `srwj_matched_all_*.xlsx` 의 **J열(한국어)** 만 수정 (K열=일본어 원문은 참고용)
- 전투: `battle_dialogue*.json` 의 `ko` 필드만 수정
- 메뉴/용어: `translations.json` 의 `ko` 필드만 수정
- 공통: 카타카나/히라가나·장음 `ー` 가 남아 있으면 미완성. `#| %s %-d &G 「」、。・` 등 제어·기호는 그대로 둘 것. 수정 후 해당 단계 빌드 스크립트를 다시 실행하세요.

---

## 저작권 / 라이선스
- 본 저장소는 **팬 번역(2차적 저작물) 도구·데이터**입니다. 원작 『슈퍼로봇대전 J』 및 등장 작품의 모든 권리는 각 권리자(반프레스토/반다이남코 등)에 있습니다.
- 게임 ROM·그래픽·폰트 원본은 포함하지 않습니다. 배포물은 ROM을 포함하지 않는 `xdelta` 차분 패치뿐입니다.
- 본인이 합법적으로 소유한 ROM에 한해 개인적 용도로 사용하세요.
