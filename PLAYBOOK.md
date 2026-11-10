# 본선 당일 플레이북 (2026-11-11, 코엑스)

`hx` = `python "D:\SKHynix-Final-Prep\hx"` (표준 라이브러리만 사용, 네트워크 불필요)

## 전날 밤 (30분)

1. `practice/task` 폴더에서 아래 "시작" 절차를 그대로 한 번 해 본다. 정답 예시는 `practice/worked`.
2. Codex와 Claude Code가 각각 `.hx/GUIDE.md`를 읽고 `hx` 명령을 쓰는지 확인한다(Claude Code는 확인됨, Codex는 미확인).
3. 노트북 충전기, 유선 LAN 어댑터.

## 08:00~09:30 현장 확인

```powershell
python "D:\SKHynix-Final-Prep\hx" doctor --net
```

운영진에게 물을 것: ① 사전 준비한 코드·도구 사용 가능 여부 ② 허용 AI 도구/모델(Codex, Claude Code, API 키) ③ 인터넷 범위(pip, GitHub) ④ 제출물 형태와 방법 ⑤ 점심 시간 작업 가능 여부 ⑥ 결과물 안에서 LLM API 호출 가능 여부 ⑦ 과제 데이터의 외부 전송 제한.
사전 도구가 금지되면 hx 없이 진행하고, 아래 "첫 프롬프트"의 절차 부분만 직접 말로 지시한다.

## 09:30 시작 (과제 폴더에서)

```powershell
python "D:\SKHynix-Final-Prep\hx" init --deadline 16:00 --git
```

과제 원문을 `docs/PROBLEM.md`로, 데이터를 `data/`에 두고 에이전트를 이 폴더에서 연다. 첫 프롬프트:

```text
.hx/GUIDE.md를 먼저 읽고 그 절차대로 진행해. 과제 원문은 docs/PROBLEM.md, 데이터는 data/에 있다.
1) hx doctor 2) 요구사항을 hx req로 등록하고 모호한 점은 hx ask로 가정과 함께 기록
3) hx profile로 데이터 확인 후 HIGH/MED 항목 처리 방침 제시
여기까지 하고 요구사항 표와 질문 목록을 보여 준 뒤, 내 확인을 받고 MVP 구현으로 넘어가.
```

## 시간 배분 (hx status가 남은 시간과 행동을 알려 준다)

| 시각 | 할 일 |
|---|---|
| 09:30~10:15 | 원문 정독, 요구사항 장부, 데이터 프로파일, 질문 정리 |
| 10:15~11:30 | 입력→핵심 로직→출력 MVP, 첫 `hx snap` |
| 11:30~14:30 | MUST를 하나씩: 구현 → `hx run --req` → `hx regress` → `hx snap` |
| 14:30 | 기능 동결. 실패 수정과 회귀만 |
| 15:15 | `hx gate --final`, README(실행법·접근·검증·가정·한계), 마지막 `hx snap` |
| 15:45 | 변경 중지, 제출 |

## 수시로 내가 치는 명령

```powershell
python "D:\SKHynix-Final-Prep\hx" status
```
```powershell
python "D:\SKHynix-Final-Prep\hx" gate --final
```
```powershell
python "D:\SKHynix-Final-Prep\hx" back
```

`back`은 계획만 보여 준다. 실제 복귀는 `--yes`. 버린 작업은 `hx-abandoned-*` 브랜치에 남는다.

## 에이전트가 "완료"라고 할 때

`hx gate --final` 출력에 `GATE: PASS`가 있는지만 본다. BLOCK/STALE/zero_tests/weak가 있으면 완료가 아니다.

## 비상

- 에이전트가 같은 실패를 반복: "멈추고 원인 가설 2개와 확인 방법을 말해"
- 코드가 망가짐: `hx back --yes` → `hx regress`
- 네트워크 차단: hx와 `hx new app` 골격은 오프라인에서 동작. pip·CDN 의존 코드를 쓰지 않게 지시
- Excel 파일: 이 PC에는 openpyxl이 없다. 읽기는 `hx profile file.xlsx`, 코드에서는 `from hx.tableio import load_table`
