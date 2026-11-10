# Codex 인수 및 안정화 상태

갱신: 2026-11-11 (KST). 본선 운영·학습 기록 보완, 실제 Cofa/Linux 확인 남음.

## 최신 체크포인트 — 본선 전 최종 점검(시간·Git 식별자)

- 시간: `--deadline`은 선택 사항. 행사 종료 16:00은 서술형 포함일 수 있어 코딩 마감으로 고정하지 않는다. hx-main은 실제 코딩 제한시간·제출 조건을 확인해 우선순위를 조정하고, 미설정 상태 메시지에서 16:00 예시를 제거했다. README 첫 프롬프트에 실제 코딩 제한시간 분석을 추가했다.
- Git 식별자: `hx snap`/`phase next`의 기존 임시 식별자 `hx <hx@localhost>`(설정 미변경)를 스킬·GUIDE·README 복구 표에 연결하고 직접 커밋용 `git -c ...` 방법을 명시했다. 직전 보완의 “커밋 시 실제 정보 요청” 문구를 공식 제출 한정으로 바로잡았다.
- 기존 요구사항(초기 WIP·단계별 커밋·중요 선택 사용자 확인·DM 기록·메인/중재 병행·독립 검토·요구사항별 테스트·LEARNING·최종 검증)은 코드·스킬·README에 반영돼 있어 변경하지 않았다.
- 근거: `docs/evidence/final-check-2026-11-11.log`.

## 이전 체크포인트 — hx run 감시 범위·실제 정보 요청·Git 승인

- 독립 검토 지적: `--watch` 없이 또는 `data/*`처럼 넓게 감시하면 결과 CSV/JSON 생성이 `source_changed_during_run`으로 실패. 판정 규칙은 유지하고, 실행 중 바뀐 감시 파일 경로와 `--watch` 수정 안내만 출력하도록 최소 수정(`hx/ledger.py`, 파일별 해시 `hx/util.py`; 기존 fingerprint 값 동일).
- hx-main 스킬·GUIDE: 실제 입력·코드만 감시, 출력·넓은 패턴 금지, 요구사항별 체크포인트, 커밋 권한 승인은 정상 절차·불가 시 PLAN 기록. 이름·이메일 등 실제 정보는 사용자에게 요청하고 테스트 데이터와 구분, 코드·기록·커밋에 저장하지 않음(hx-ship에도 확인 추가).
- README: 메인 첫 프롬프트에 실제 정보 요청 한 줄, 복구 표에 커밋 승인·`source_changed_during_run`·실제 정보 요구 3행. 깨진 링크 원인이던 미커밋 `cofa-final-*` 근거를 민감정보 점검 후 커밋.
- 근거: `docs/evidence/hx-run-watch-2026-11-11.md`.

## 이전 체크포인트 — 실제 작업 공간·별도 세션·학습 기록

- 이번 사용자 요청에 맞춰 처음 열린 Cofa 현재 폴더를 기본 작업 공간으로 안내한다. README는 두 줄 설정·정상 문구·Codex·메인 프롬프트·필요할 때 별도 중재·10가지 복구 문장·쉬운 용어 순서로 정리했다. 기본 명령은 공개 Clone 후 `/tmp/sk-harness/hx init` 그대로다.
- 최소 코드 변경: 기존 init에 한국어 `collab/LEARNING.md` 양식 생성과 안내만 추가했다. 기존 파일은 `_create`로 보존한다. 메인·중재·제출 스킬과 PLAYBOOK/GUIDE에 실제 코드·R/D/Q·DM·검증·커밋 근거의 학습 기록, 별도 세션의 컨텍스트·사용량 비공유, 서술형 제한 시 AI 도움 중단을 연결했다.
- 변경 전 관련 13개 PASS, 변경 후 `test_project`+`test_collab` 32개 PASS(309.563초). TEMP 독립 과제에서 파일·충돌 보존, 학습 갱신·재초기화 보존, 공유 상태·장부·중재 조회, Git 기준점·WIP, 실패·잘못된 경로의 비파괴 복구 PASS. 준비 저장소·ex-harness·기존 rehearsal에는 init하지 않았다.
- 실제 CLI AGENTS/학습 지침 주입과 네 hx 스킬 enabled 확인. 번들 스킬 검사기는 PyYAML 미설치로 실행 불가이며 설치로 우회하지 않았다. 로컬 Astra High 별도 메인에서 스킬 본문 읽기·hx 진단/분석·요구사항/결정/DM 질문 등록을 관찰했으나 240초 한도로 계획·학습 갱신·모델 주도 커밋은 미완료다.
- WSL 배포판·Docker/Podman이 없어 실제 Linux 실행 미검증. Git Bash는 기본 두 줄 구문만 PASS. 실제 Cofa 다중 터미널·Sol 6.1 High·추론 조절·신뢰된 네이티브 훅은 현장 확인 대상이다. 기본 훅 비활성·전역 설정/도구 변경 없음.
- GitHub 연결 도구로 올바른 공개 origin/main 확인, 일반 자격증명 패턴 및 공개 파일 범위 검사 완료. 이번 요청은 검증·로컬 커밋·조건 충족 후 origin/main push를 명시적으로 승인했다. 본선 과제의 외부 전송 승인으로 확대하지 않는다.
- 근거: `docs/evidence/cofa-final-2026-11-11.md`와 연결 로그. 실행 스크립트·원본 모델 이벤트는 비공개 `.audit-work/final`, 이전 연습은 `.audit-work/rehearsal`로 분리한다.

## 이전 체크포인트 — 새 노트북 시작 절차

- README는 실제 과제 루트에서 `/tmp/sk-harness`로 Clone 후 기존 `hx init`을 적용하는 두 명령, 적용 확인, 메인·중재 첫 프롬프트로 재작성했다. PLAYBOOK은 상황별 복사 프롬프트, 세부 운영·안전 규칙은 `docs/OPERATIONS-REFERENCE.md`로 정리했다.
- 런타임 코드·설치 프로그램은 변경하지 않았다. hx-main 스킬에 최초 경로·로딩·장부·Git 점검과 초기 WIP 체크포인트만 보완했다.
- 현재 노트북: Windows Python 3.12.10, Git 2.51.0, Codex CLI 0.165.0. 아래 과거 환경의 0.166.0·WSL 기록과 구분한다. WSL 배포판 없음. Linux 문법 확인과 실제 Linux 실행을 구분했다.
- 관련 기존 테스트 9개 PASS, 변경 후 설치 테스트 3개 PASS. 운영체제 TEMP의 독립 과제에서 doctor/init/파일 보존/공유 문서/요구사항/중재 장부/Git 기준점·WIP 커밋 확인. 준비 저장소 자체와 ex-harness에 init하지 않았다.
- 실제 CLI prompt-input의 AGENTS 주입, skills/list의 네 hx 스킬 enabled 확인. 로컬 Astra High 실행은 Windows 샌드박스의 임시 경로 접근 거부로 본문 읽기·hx 실행·모델 주도 체크포인트를 완료하지 못했다. 권한·신뢰·전역 설정 우회 없음. 네이티브 훅·Cofa 실행은 미검증.
- 근거: `docs/evidence/cofa-startup-2026-11-10.md` 및 연결된 로그. 원본 프롬프트·이벤트는 비공개 `.audit-work/startup`에만 보관. 개인 ZIP·세션 백업 복원 없음.
- 이번 사용자 요청은 관련 변경 검증·커밋과 비밀정보 점검 후 GitHub push까지 명시적으로 승인했다. 과거의 원격 push 금지/확인 대기는 이번 한정 작업에 적용하지 않는다. 본선 과제의 외부 전송 허용으로 확대하지 않는다.
- 배포 확인: 사용자 GitHub 로그인 후 `54bdd3d`를 origin/main에 push했고 원격 SHA 일치를 확인했다. 공개 GitHub에서 새 TEMP 폴더로 Clone한 수정본으로 init/status·입력 보존·갱신 스킬 설치·기본 훅 비활성을 확인했다(`docs/evidence/cofa-public-clone.log`). Windows 검증이며 Cofa/Linux 실행 증거는 아니다.
- 현장: 과제·제출 루트, Clone·사전 코드·Python 허용, Python 3.10+, 제공 Codex 권한과 Sol 6.1/High, 제출 방식 확인. 읽기 권한 오류는 정상 플랫폼 절차로 해결하고 첫 프롬프트로 실제 적용을 재검증한다.

## 이전 준비·연습 기록 (보존)

- 목표: 11/11 Cofa에서 사용자 결정, 구현, 독립 검토, 검증, 단계별 Git 기록을 연결하는 최소 협업 체계.
- 인수: 폴더에 Git/루트 README/이전 테스트 로그 없음. Claude 최종 PASS는 미확인.
- 보존: `audit/codex-handoff`, 인수 파일 기준점 `aca1002`. ex-harness는 읽기 전용 참고.
- 확인: Windows Python 3.12, Ubuntu 24.04 Python 3.12.3, Codex CLI 0.166.0. AGENTS prompt 주입과 네 스킬 활성 로딩, 프로젝트 훅 파싱 관찰. 훅은 untrusted여서 네이티브 이벤트 실행 미검증. 전역 설정·신뢰 우회 없음.
- 재현된 결함: 병렬 검사 기록 유실, 전부 skip PASS, 삭제·데이터 변경 후 stale 누락, high 검토 handled로 gate 우회, 프롬프트 시각을 승인으로 과장.
- 검증: Windows 전체 91개 PASS(307.098초), WSL 전체 91개 PASS(122.138초). 추가 연습 발견 수정 후 Windows 감사17개·프로파일12개 PASS, WSL 관련29개 PASS. 최종 인수 점검에서 추가된 평가기 11개를 포함한 Windows 전체 `tests/` 105개 PASS 및 `practice/reference/etch-schedule` 7개 PASS 확인(`practice/reference/etch-schedule/scheduler.py`의 Windows 파이프 UTF-8 출력 재설정 결함 수정 포함). 로그 `docs/evidence` 및 `.audit-work`.
- 수정 체크포인트: `d054f65`. 이후 미응답 질문 gate 차단·응답 예시 수정, 독립 평가기(`practice/evaluate_pm.py`) 및 테스트(`tests/test_practice_evaluator.py`), 참고 스케줄러 Windows 파이프 인코딩 수정, 운영 문서 정리 완료.
- 실제 사용자 결정: 연습 D1=A SciPy MILP, 모의 담당자 답변 제공 승인. 메인 Sol 6.1 High가 질문·대기·분석 WIP 커밋을 실제 수행했고 사용자 응답 후 재개. 중재 Sol 6.1 Medium은 읽기와 리뷰 등록. 모의 담당자 답변은 실제 DM과 구분.
- 연습: `.audit-work/rehearsal`, 기준 `cd4a2ef`, 분석 `40994a6`, 이후 단계별 커밋(`f9aeb74`). 메인/중재 최신 장부 확인. `schedule_pm.py` 및 자체 검증 `verify_pm.py` 6개 테스트 PASS(탐욕 기준선 47점/14건, SciPy MILP 51점/16건, gap 0%). 독립 평가기(`practice/evaluate_pm.py`) 대조 시 필수 열(`job_id,eng_id,start,end` 및 `job_id,reason`) 기준 규칙 위반 0건·가중치 점수 51점 확인(단, 풀이 세션에 `ANSWERS.md`의 4열 제한이 전달되기 전 한도에 도달해 실제 CSV는 설비·bay·자격·이름을 포함한 10열로 출력됨).
- 모델 정책: 로컬 Astra High. 본선 메인/중재/가능한 하위는 Sol 6.1 우선, 현장 규정과 실제 모델 목록 우선. High 출발, 간단한 작업 Low/Medium, 어려운 판단 Extra High. 현재 세션 자동 변경 수단 미확인; 전역 설정 변경 없음.
- 승인: 프로젝트 수정/테스트/로컬 커밋 허용. 원격 저장소 생성 및 push는 사용자 최종 확인 후 수행. ex-harness 수정/전역 설정·업데이트 금지.
- 다음: Codex 한도 복구 시 `.audit-work/rehearsal`에서 출력 열 스키마(4열/2열) 정합성 반영 → 모의 변경(E2 00:00~01:00 시간 제한, `--e2-block`) 반영 → 중재 재검증·리뷰(V1·V2) 종료 및 요구사항 완료(`hx gate --final`, `hx ship`). Cofa 현장·신뢰 후 네이티브 훅·모델별 토큰 성능 비교는 아직 미검증.
