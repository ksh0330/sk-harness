# Cofa 시작 절차 검증 — 2026-11-10 (KST)

이번 작업은 기존 `hx init`과 지침을 활용한 시작 절차 정리다. 새 설치 프로그램·런타임 기능·대형 테스트는 추가하지 않았다. 최신 사용자 요청의 문서·검증·커밋·조건 충족 후 push 범위만 수행한다.

## 확인 결과

| 구분 | 이번 노트북에서 관찰한 결과 |
|---|---|
| 실행 환경 | Windows, Python 3.12.10, Git 2.51.0.windows.1, Codex CLI 0.165.0 |
| 초기 Git | `main`, 깨끗한 작업 트리. `git fetch origin` 후 `HEAD...origin/main` = `0 0`, 기준 `4f1b364` |
| 관련 기존 테스트 | `$env:PYTHONPATH='tests'; python -B -m unittest test_project.Init test_project.Checkpoints test_project.NoRepo -v` → 9개 PASS, 58.563초 |
| 과제 격리 | 운영체제 TEMP 아래 새 `hx-startup-*`의 `task with spaces`와 `preserve`. 준비 저장소·ex-harness·이전 rehearsal에 init하지 않음 |
| doctor | 별도 과제 cwd에서 실행, `DOCTOR: OK`, 네트워크 미탐색 |
| init·공유 문서 | AGENTS·4개 스킬·GUIDE·BOARD·INBOX 생성. 기본 훅 파일 없음 |
| 보존 | 입력 CSV 내용, 기존 AGENTS와 충돌하는 hx-main 스킬 바이트 그대로 보존 |
| 요구사항·상태 | 빈 장부 조회, 요구사항 등록, now/status/audit, 중재 review add/prompt 성공 |
| Git | 격리 과제에서 `init --git` 기준점 `e7a33a4`, `snap --wip` 초기 요구사항 체크포인트 `b048b6e` 실제 생성 |
| CLI 지침 로딩 | `codex debug prompt-input` 종료 0, 과제 AGENTS 본문과 hx-main/hx-mediator 메타데이터 포함 |
| 스킬 발견 | 실제 `codex app-server`의 `skills/list`에서 hx-main/design/mediator/ship 모두 enabled=true |
| 모델의 실제 수행 | 로컬 `gpt-6-astra`, High, `codex exec --ephemeral --json -s workspace-write`로 README 메인 프롬프트 실행. Windows 샌드박스 경로 접근 거부로 본문 읽기·hx 실행·모델 주도 커밋은 미완료 |
| Linux | `wsl --list --quiet` 종료 0, 배포판 목록 비어 있음. 시스템 설치·업데이트 없이 종료. README Bash 구문은 Git Bash `bash -n` 통과, 실제 Linux 실행과 구분 |
| Cofa·네이티브 훅 | 이번 검증 대상에 접근할 수 없어 미검증. 훅 비활성, 신뢰 우회 없음 |

## 실제 모델 실행의 한계

모델이 작업 디렉터리를 지정해도 도구의 PowerShell 위치가 셸 설치 경로로 나타났다. 모델은 경로 불일치를 감지하고 과제의 절대 경로로 재시도했으나 다음 오류를 받았다.

```text
Access to the path '<TEMP>/task with spaces' is denied.
Access to the path '<TEMP>/task with spaces/AGENTS.md' is denied.
Access to the path '<TEMP>/task with spaces/.agents/skills/hx-main/SKILL.md' is denied.
fatal: cannot change to '<TEMP>/task with spaces': Permission denied
```

모델은 성공을 주장하지 않고 미확인 항목과 커밋 불가를 보고했다. 프로세스 종료 0은 작업 성공을 뜻하지 않는다. 이 문제를 피하려고 샌드박스·전역 설정·신뢰를 완화하지 않았다. 메인과 중재의 스킬 **발견**은 확인했지만 현재 노트북의 두 모델 세션 협업 완료를 주장하지 않는다. 수동 CLI 스모크의 커밋은 모델이 만든 것으로 계산하지 않는다.

기존 `docs/evidence/codex-runtime.json`과 STATE의 WSL·모델 연습 기록은 이전 환경의 증거다. 현재 노트북의 CLI 버전·WSL 유무와 다르므로 이번 결과로 대체 해석하지 않는다. 개인 세션 백업은 복원하지 않았다.

## 재현 명령과 기록

- [설치·보존·장부·Git 명령 출력](cofa-startup-commands.log): 임시 경로를 `<TEMP>`로 치환. 테스트 fixture만 포함.
- [CLI 로딩·발견·모델 결과 요약](cofa-startup-runtime.json): 실제 prompt-input과 skills/list에서 필요한 필드만 추출.
- [수정 후 init 테스트](cofa-startup-init-tests.log): 변경된 스킬을 포함한 3개 설치 테스트.
- 전체 프롬프트 덤프·모델 원본 이벤트·실행용 임시 스크립트는 Git 제외 `.audit-work/startup`에 보관. 공개 저장소에는 개인 대화·인증 파일을 추가하지 않는다.

## 시작 명령의 판단

`python3 sk-harness/hx init`은 **현재 폴더**를 대상으로 하므로 원래 두 명령도 Linux 경로 문법과 코드상 실행 가능하다. 하지만 clone이 과제 안에 들어가 전체 폴더 제출에 섞일 수 있다. 따라서 실제 과제 루트에서 다음을 권장한다.

```bash
git clone https://github.com/ksh0330/sk-harness.git /tmp/sk-harness &&
python3 /tmp/sk-harness/hx init
```

`&&`는 clone 실패 시 다음 명령을 중단한다. 과제·제출 범위가 `/tmp/sk-harness`를 포함하지 않는지, 해당 경로를 쓸 수 있는지, 실제 과제 루트가 맞는지는 현장에서 확인해야 한다. init은 과제의 의미를 자동으로 판별하지 않는다. Python 3.10 이상, 제공 Codex 권한·모델 목록, 사전 코드·Clone 허용, 제출 절차도 현장 확인 사항이다.

스킬 본문 로딩과 메타데이터 발견의 구분은 [공식 스킬 안내](https://learn.chatgpt.com/docs/build-skills), 신뢰 없는 훅의 한계는 [공식 훅 안내](https://learn.chatgpt.com/docs/hooks)와 대조했다. 공식 기능 문서는 Cofa 허용의 근거가 아니다.
