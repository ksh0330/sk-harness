# hx 명령 안내

`hx` = `{HX}`. Python 표준 라이브러리만 쓰며 네트워크가 필요 없다. 기록은 `.hx/`에 쌓이고, 사람이 보는 요약은 `collab/BOARD.md`에 자동으로 만들어진다. 절차는 `hx-main`(메인 세션), `hx-design`(대안 평가), `hx-mediator`(중재 세션), `hx-ship`(제출) 스킬에 있다.

## 과제 파악

| 명령 | 하는 일 |
|---|---|
| `hx intake` | 문서(PDF·DOCX·PPTX·HWPX는 텍스트로 추출), 데이터 파일 요약, 기존 코드, 환경을 한 번에 정리 |
| `hx doctor` | 이 환경에서 쓸 수 있는 도구·라이브러리와 없는 것의 대체 수단 |
| `hx profile data/a.csv data/b.xlsx` | 타입·결측·중복·이상값·키·파일 간 참조 깨짐 |
| `hx req add "..." --kind must --accept "확인 방법"` / `hx req add --file reqs.txt` | 요구사항 등록 (R1, R2 …) |
| `hx req set R3 --status done` / `--status dropped --decision D2` | 상태 변경. MUST를 빼거나 낮추려면 사용자 결정 번호가 필요 |

## 사용자·담당자와의 소통

| 명령 | 하는 일 |
|---|---|
| `hx ask "질문" --assume "가정"` | 사용자에게 물을 질문과 답이 없을 때의 가정 |
| `hx ask "질문" --to dm --why "이유" --assume "가정"` | 사용자가 과제 담당자에게 DM으로 보낼 질문 |
| `hx answer Q2 "답 원문" [--source dm]` | 받은 답을 그대로 기록 |
| `hx decide add "제목" --option "A: ..." --option "B: ..." --recommend A --why "..." --impact "..."` | 사용자가 정할 사항을 대안·권장안과 함께 등록 |
| `hx brief` | 이해한 과제, 질문, 정할 사항을 사용자에게 보여 줄 형태로 출력. 보여 준 뒤 멈추고 기다린다 |
| `hx decide set D1 --choice A --note "사용자 원문"` | 사용자의 결정을 기록 |
| `hx decide log "항목" --choice "선택" --why "이유"` | AI가 스스로 내린 작은 결정을 기록 |
| `hx feedback add "사용자 지시 원문"` / `hx feedback done F1 --note "바꾼 것"` | 방향을 바꾸는 피드백의 접수와 처리 |
| `hx inbox` | `collab/INBOX.md`에서 아직 읽지 않은 부분 |

## 진행과 상태

| 명령 | 하는 일 |
|---|---|
| `hx phase` / `hx phase next --user-said "..."` / `hx phase set design --note "이유"` | 단계 확인, 다음 단계로(조건 확인 후 커밋), 되돌아가기 |
| `hx now "하고 있는 일" --next "다음 일"` | 현재 작업 표시 (보드와 중재 세션이 본다) |
| `hx status` | 남은 시간, 요구사항별 증명 상태, 결정, 검토 의견 |

## 검증

| 명령 | 하는 일 |
|---|---|
| `hx run --name unit --req R1,R2 --done -- python3 -m unittest -v` | 명령을 실행하고 로그·종료 코드를 증거로 남김. 통과하면 연결된 요구사항을 done으로 |
| `hx run --name x --sh "명령 한 줄"` | 문자열 명령으로 실행. `--expect 정규식`, `--metric "f1=F1: ([0-9.]+)"`, `--watch "app/*,rules.json"`(이 파일들이 바뀔 때만 다시 필요) |
| `hx check rules.json` / `hx check --draft data/*.csv -o rules.json` | 입력과 산출물의 규칙 검증. `expr`에서 `ref('lots','lot_id',lot_id,'proc_min')`로 다른 표 조회, 표를 리스트로 주면 합집합 |
| `hx smoke smoke.json` | 서버 기동 → 응답 확인 → 종료 |
| `hx regress` / `hx regress --stale` / `hx regress --no-record` | 모든 검사 재실행 / 통과 상태가 아닌 것만 / 기록 없이(중재 세션용) |
| `hx gate` / `hx gate --final` | 완료를 막는 항목. `--final`은 먼저 전부 다시 돌림 |
| `hx ship` | 최종 검사와 제출 보고서 `collab/REPORT.md` |

STALE은 증명 이후에 감시 대상 코드·데이터가 바뀌거나 삭제됐다는 뜻이다. 검증 중 감시 대상이 바뀌어도 실패로 처리한다. 산출물을 생성하는 명령은 `--watch "src/*,data/*,tests/*"`처럼 실제 입력·코드 의존 범위를 지정하고 산출물 검사는 별도 명령으로 수행한다. 테스트가 0개 실행됐거나 `echo` 같은 명령은 증거로 치지 않는다.

## Git

| 명령 | 하는 일 |
|---|---|
| `hx snap "설명"` | 실질적인 검사가 하나 이상 있고 모두 PASS인 상태를 커밋하고 `hx-ok-N` 태그 |
| `hx snap --wip "설명"` | 진행 중인 상태를 태그 없이 커밋 (분석·계획 문서, 깨진 중간 상태) |
| `hx back` / `hx back --yes` | 마지막 `hx-ok`로 되돌릴 계획 / 실행. 버린 작업은 `hx-abandoned-*` 브랜치에 남는다 |

커밋에는 의존성 폴더, 25MB 넘는 파일, `.env`, 과제 폴더 안에 받은 hx 자체는 들어가지 않는다. push는 하지 않는다. 기존 stage가 있으면 자동 커밋을 거부한다. `snap`과 `phase next`는 전체 과제 트리를 stage하므로 무관한 변경이 섞인 폴더에서는 사용하지 않는다. 검토한 파일만 직접 커밋하고 `phase set <단계> --note "수동 체크포인트 해시와 실제 승인 근거"`로 상태를 기록한다.

## 중재 세션

| 명령 | 하는 일 |
|---|---|
| `hx audit` | 장부와 실제(git·증거·파일)의 불일치를 찾는다. 파일을 수정하지 않는 조회 |
| `hx review add "문제" --severity high --evidence "근거" --ask "요청"` | 검토 의견 등록 (V1 …) |
| `hx review prompt` | 메인 세션에 붙여넣을 프롬프트 생성 |
| `hx review done V1 --note "조치"` (메인) / `hx review close V1` / `hx review reopen V1 --note "..."` (중재) | 처리, 확인, 재요청 |

## 환경에서 지킬 것

- `collab/LEARNING.md`는 메인이 한국어로 관리하는 학습 기록이다. 단계마다 핵심 개념·기술 선택·대안·데이터 흐름·예외·문제 해결·검증 수치·실제 사용자 결정과 DM·한계를 실제 코드·장부·로그·커밋에 연결한다. 중재는 읽고 설명하며 수정 요청만 전달한다. 미확인 구현·수치를 만들지 않는다.
- 학습 기록은 AI 사용이 허용된 코딩 단계에서 준비한다. 서술형에서 AI·붙여넣기 금지가 적용되면 그 단계에서는 AI를 사용하거나 AI 답변을 붙여 넣지 않으며, 사용자가 이해한 내용으로 직접 작성한다. 기록 열람도 현장 규정을 따른다.

- 대회 환경의 도구와 Codex를 업데이트하지 않는다. 패키지 설치는 과제 안내가 허용하고 사용자가 승인했을 때만 한다. `hx doctor`에 있는 것으로 먼저 푼다.
- 과제 자료·코드·결과물을 플랫폼 밖으로 보내지 않는다. push하지 않는다.
- 파일을 열 때 `encoding`을 명시한다(읽기 `utf-8-sig`, 실패하면 `cp949`). `.xlsx`는 `hx profile`이 읽고, 코드에서는 `from hx.tableio import load_table`을 쓸 수 있다.
- 웹 서버는 과제 안내가 정한 주소·포트를 따르고(없으면 `0.0.0.0`과 출력한 포트), 테스트용 서버는 끝나면 내린다.
- 난수는 seed를 고정한다. 같은 입력에 같은 출력이 나와야 재현된다.
