# 본선 빠른 시작

**과제 폴더에서 아래 순서대로 시작하세요.** 하네스 명령과 스킬 이름은 외우지 않아도 됩니다. 이후에는 메인 Codex에 자연어로 요청하세요.

현장에서 공개 Git Clone·사전 코드·Python 실행이 허용될 때 사용합니다. 제공 도구 업데이트·전역 설정 변경은 하지 않습니다. **메인·중재 모두 Sol 6.1 / High 우선**, 실제 제공 목록과 현장 규정이 우선입니다. Claude·Astra는 본선에서 사용하지 않습니다.

## 1. Git Clone

먼저 `pwd`와 `ls -la`로 **과제 원문·제공 자료가 있는 실제 과제 루트**인지 확인하세요. 다른 위치라면 그 폴더로 `cd`하세요. `/home/user`라고 단정하지 않습니다. Git이 있다면 `git rev-parse --show-toplevel`도 대조합니다.

아래 두 명령을 한 번에 복사하세요. **`cd sk-harness`는 하지 않습니다.** `/tmp/sk-harness`는 과제·제출 폴더 밖이어야 합니다.

```bash
git clone https://github.com/ksh0330/sk-harness.git /tmp/sk-harness &&
python3 /tmp/sk-harness/hx init
```

## 2. 하네스 적용

위 두 번째 명령이 현재 과제 폴더에 적용합니다. 별도 설치·패키지 다운로드는 없습니다. 기존 과제 파일·AGENTS.md·스킬은 덮어쓰지 않으며, 충돌 파일은 `kept existing`으로 알립니다. 기본값은 **훅 없이** 동작하고 Git 커밋은 첫 프롬프트에서 검토 후 만듭니다.

`/tmp/sk-harness`가 이미 있으면 Clone은 중단됩니다. 지우거나 덮어쓰지 말고 출처를 확인하거나 다른 과제 밖 경로를 사용하세요. 작업 중 하네스 경로를 옮기지 마세요. `/tmp`는 환경 재시작 시 없어질 수 있습니다.

## 3. 적용 확인

초기화 출력의 `hx initialised in ...`이 **실제 과제 루트**인지 확인하세요.

```bash
python3 /tmp/sk-harness/hx status
```

`.hx/config.json`, `collab/BOARD.md`, `collab/INBOX.md`, `.agents/skills/hx-main/SKILL.md`와 `hx-mediator/SKILL.md`가 준비됩니다. 처음에는 요구사항 0개가 정상이며 첫 등록 때 요구사항 파일이 생성됩니다. 파일 생성과 Codex의 실제 적용은 다릅니다. 다음 프롬프트가 실제 점검을 요청합니다.

## 4. Codex CLI 실행

**같은 과제 루트**에서 실행합니다. 제공 화면에서 허용 모델 Sol 6.1과 High를 확인하세요. 모델 ID를 추측하거나 기존 도구를 업데이트하지 않습니다.

```bash
codex
```

## 5. 메인 세션 첫 프롬프트

```text
메인 세션으로 시작해. 현재 폴더가 실제 과제 루트인지 원문·제공 자료·Git 루트로 확인해.
적용되는 AGENTS.md, .agents/skills/hx-main/SKILL.md와 .hx/GUIDE.md를 읽어.
스킬의 목록 인식·직접 읽기·실제 절차 수행을 구분해서 보고해. 파일 존재만으로 적용 성공이라 하지 마.
GUIDE의 실제 hx 명령으로 --version, doctor(네트워크 제외), status, req list를 실행하고
공유 BOARD·INBOX, 기존 Git 변경·stage·최근 커밋, 과제 원문·자료·평가·제출 조건을 확인해.
초기 상태와 명시된 요구사항·검증 방법·미확정 사항을 장부와 collab/PLAN.md에 기록해.
로컬 Git 초기화와 관련 파일의 초기 WIP 커밋을 허용한다. 기존 파일·변경·stage는 보존하고,
상위 저장소에 영향을 주지 마. 의미 있는 초기 기록을 커밋하고 해시 또는 못 한 이유를 알려줘.
이어서 요구사항 분석을 주도해. 중요한 해석·알고리즘·스택·아키텍처·범위는
대안과 권장안을 제시하고 내 실제 답을 기다려. 담당자 DM은 내가 보낼 문장으로 제시해.
일반 조회·구현·테스트는 승인된 범위에서 계속하고, 단계마다 검증·변경 파일·Git·다음 일을 기록해.
훅 없이 진행하고 도구 업데이트·전역 설정 변경·원격 push는 하지 마.
```

## 6. 중재 세션 첫 프롬프트

별도 터미널에서 **같은 과제 루트**로 이동하여 `codex`를 실행하고 붙여 넣습니다.

```text
중재 세션으로 시작해. 적용되는 AGENTS.md와 .agents/skills/hx-mediator/SKILL.md를 읽고,
스킬 인식·직접 읽기 여부를 구분해 알려줘. .hx/GUIDE.md의 hx 명령으로 status와 audit를 확인해.
과제 원문, BOARD·PLAN, 요구사항, 실제 코드·테스트 근거, Git 상태·diff·최근 커밋을 대조해.
필요한 사용자 결정과 누락·모순·위험을 근거로 설명하고 메인에 붙일 짧은 수정 요청을 작성해.
코드·계획·Git·설정은 수정하지 마. 검토 기록만 hx review로 남기는 것을 허용한다.
검사를 재실행할 때는 내용을 먼저 확인하고 격리 환경이나 안전한 검사만 사용해.
메인을 직접 제어한다고 가정하지 말고, 조치된 의견은 근거를 재확인한 뒤 종료해.
```

## 환경이 다를 때만

- **Python:** 3.10 이상이 필요합니다. `python3`가 없고 `python --version`이 조건을 만족하면 `python3`만 `python`으로 바꾸세요. 없으면 설치로 우회하지 말고 아래 대안을 사용하세요.
- **과제 경로 지정:** 다른 폴더에서 적용하려면 `python3 /tmp/sk-harness/hx --root "/실제/과제/경로" init`. Codex는 그 과제 폴더에서 시작합니다.
- **Windows PowerShell:** 과제 루트에서 `git clone https://github.com/ksh0330/sk-harness.git "$env:TEMP/sk-harness"` 후 `python "$env:TEMP/sk-harness/hx" init`. TEMP도 과제 밖인지 확인하세요.
- **훅:** 기본 절차에 불필요합니다. CLI 지원·현장 허용·사용자 선택·Codex 신뢰 승인이 모두 확인된 경우에만 사용합니다. [세부 참고](docs/OPERATIONS-REFERENCE.md).

## 반입·Python이 불허되면: 직접 프롬프트

설치나 제한 우회 없이 제공 Codex에 입력합니다.

```text
현재 과제 원문·자료·평가·제출 규정·기존 지침·Git 상태부터 확인해.
요구사항, 검증 방법, 내 결정과 실제 담당자 답변, 현재 상태와 다음 일을 공유 Markdown에 기록해.
중요한 해석·알고리즘·스택·아키텍처·범위는 대안·권장안을 제시하고 내 답을 기다려.
담당자 DM은 내가 보낼 문장으로 만들어. 승인된 조회·구현·테스트는 자율적으로 계속해.
의미 있는 단계마다 검증 결과와 관련 파일의 로컬 Git 체크포인트를 남겨.
별도 중재는 코드·Git을 수정하지 않고 근거와 수정 요청을 나에게 전달하게 해.
현장 규정을 우선하고 도구 업데이트·전역 설정 변경·외부 전송은 하지 마.
```

진행 중에는 [PLAYBOOK](PLAYBOOK.md)의 상황별 프롬프트만 사용하세요. [규정과 확인 범위](docs/COFA-RULES.md), [고급 참고](docs/OPERATIONS-REFERENCE.md), [현재 검증 결과](docs/evidence/cofa-startup-2026-11-10.md).
