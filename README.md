# SK하이닉스 AI 해커톤 본선 준비

`hx`는 요구사항, 사용자 결정, 담당자 DM, 테스트 증거, Git 체크포인트와 중재 의견을 연결하는 Python 도구다. 표준 라이브러리만으로 핵심 기능을 실행한다. **독립 감사와 실전 검증을 진행 중이며, 설치나 단위 테스트 통과를 Cofa 실전 성공으로 간주하지 않는다.**

사용 순서는 [PLAYBOOK.md](PLAYBOOK.md), 규정 근거는 [COFA-RULES.md](docs/COFA-RULES.md)를 참고한다. `D:\ex-harness`는 읽기 전용 참고 저장소이며 설치 대상이 아니다.

## 시작 (다른 PC에서 Clone 및 환경 확인)

Python 3.10 이상과 Git만 있으면 별도 패키지 설치(`pip install`)나 전역 설정 변경 없이 바로 동작한다.

```powershell
# 1. 저장소 복제 및 이동
git clone https://github.com/ksh0330/sk-harness.git
cd sk-harness

# 2. 실행 환경 진단 및 단위 테스트 확인
python -B .\hx doctor
python -B -m unittest discover -s tests -p "test_audit_evidence.py" -v
python -B -m unittest discover -s tests -v
```

> **Cofa 본선 반입 주의:** 본선 Cofa 환경에서 외부 저장소 Clone이나 사전 제작 코드 반입은 현장 규정상 허용 여부를 먼저 확인한 경우에만 사용한다. 반입이나 Python 실행이 허용되지 않으면 설치·우회를 시도하지 말고 [PLAYBOOK.md](PLAYBOOK.md)의 직접 지시 프롬프트로 진행한다.

### 무설치(표준 라이브러리) 지원 기능

외부 패키지나 네트워크 없이 Python 표준 라이브러리만으로 다음 기능이 동작한다.

- 환경 진단(`doctor`), 과제 폴더 인벤토리 및 문서(PDF 외 DOCX·PPTX·HWPX·HTML·MD·TXT) 텍스트 추출(`intake`)
- CSV·TSV·JSON·JSONL·XLSX(수식 캐시·날짜 서식 포함)·SQLite 로딩 및 결측·이상치·중복·참조 무결성 프로파일링(`profile`, `check`)
- 요구사항(`req`), 사용자 결정(`decide`, `brief`), 담당자 DM 질문·답변(`ask`, `answer`), 방향 수정(`feedback`), 공유 메모(`inbox`)
- 단계 관리(`phase`, `now`, `status`), 실행 증거 기록 및 변경 감지(`run`, `regress`, `gate`, `ship`)
- 로컬 Git 체크포인트 및 안전 복구(`snap`, `back`), 중재 감사 및 리뷰 전달(`audit`, `review`)
- 오프라인 웹 서버·UI 스캐폴딩(`new app`) 및 로컬 HTTP 스모크 검증(`smoke`)

## 과제 폴더 초기화 및 세션 시작

실제 과제 폴더에서 실행한다. `--root`는 `hx` 하위 명령 앞에 둔다. (`$HX`를 복제한 `hx` 폴더의 절대 경로로 두면 편리하다.)

```powershell
$HX = "$PWD\hx"
python $HX doctor
python $HX --root "실제 과제 폴더의 절대 경로" init
python $HX --root "실제 과제 폴더의 절대 경로" intake
```

`init`은 `.hx`, 공유 문서, AGENTS와 스킬을 준비한다. 기존 사용자 AGENTS·스킬은 보존하며 다르면 안내한다. 기존 과제 지침과 현재 사용자 요청이 우선한다. Git 저장소가 없고 로컬 초기화가 허용된 경우에만 `init --git`을 사용한다. 기존 저장소에서는 먼저 Git 상태와 변경 출처를 확인한다.

Cofa에서는 실제 Python 명령과 반입이 허용된 hx 경로로 바꾼다. Windows 경로를 그대로 붙여 넣지 않는다. Python·코드 반입이 허용되지 않으면 설치나 업데이트로 우회하지 말고 플레이북의 직접 지시로 진행한다.

메인 Codex에서 허용 모델을 선택한 뒤:

```text
.agents/skills/hx-main/SKILL.md와 .hx/GUIDE.md를 읽고 메인 세션으로 진행해.
과제 원문과 기존 지침, 데이터, Git 상태부터 확인해.
요구사항과 검증 방법을 기록하고, 결과를 바꾸는 해석·스택·알고리즘·범위 결정은
대안과 권장안을 제시한 뒤 내 답을 기다려. 이미 승인한 작업은 계속 진행해.
담당자에게 물어야 하면 대상, 보낼 문장, 목적, 답변별 영향을 알려줘.
의미 있는 단계마다 테스트 근거, Git 체크포인트, 현재 상태와 다음 작업을 남겨.
```

스킬 목록에 없으면 해당 파일을 직접 읽는다. 자동 호출과 직접 읽기를 구분해 기록한다. 기본 시작에는 Hook이 필요 없다. `init --hooks`는 CLI 지원·Cofa 허용·사용자 선택을 확인한 경우만 사용하며, 생성 후 Codex가 요구하는 신뢰 검토를 따른다. 파일 생성만으로 실행 중이라고 말하지 않는다.

## 메인·중재 협업

메인은 코드, 요구사항, 테스트와 Git의 주 작성자다. 중재는 같은 과제 폴더를 읽고 검토하며 메인을 직접 제어한다고 가정하지 않는다.

```text
.agents/skills/hx-mediator/SKILL.md를 읽고 중재 세션으로 검토해.
코드·Git·설정을 수정하지 말고 현재 상태, 필요한 사용자 결정,
요구사항과 구현·테스트·Git의 불일치를 근거와 함께 설명해.
메인에 전달할 수정 프롬프트를 작성해. 검토 기록만 hx review로 남겨.
```

`collab/BOARD.md`는 자동 생성되므로 직접 고치지 않는다. 긴 사용자 메모는 `collab/INBOX.md`에 덧붙이며 두 세션이 동시에 저장하지 않는다. 메인은 `hx inbox`로 읽고 결정·요구사항에 반영한다. 중재 의견은 `hx review add`, 메인 조치는 `done`, 중재 재검증은 `close`로 기록한다. `hx review prompt`의 전달 문장은 사용자가 메인에 붙여 넣는다.

`hx status`, `hx audit`로 장부와 실제 상태를 확인한다. `hx regress --no-record`도 테스트 명령 자체의 부작용까지 막는 샌드박스는 아니다. 중재는 실행할 검사의 내용을 먼저 확인한다.

## 모델과 사용량

| 작업 | 운영 기준 |
|---|---|
| 로컬 독립 감사·오류 수정 | GPT-6 Astra High |
| Cofa 메인·중재 | Sol 6.1 우선, 실제 허용·제공 목록 우선 |
| 하위 에이전트 | 지원·허용될 때 Sol 6.1 우선. 필요한 범위와 정보만 전달 |
| 단순 조회·상태·문서 수정 | Low/Medium 권장 |
| 분석·계획·일반 구현·디버깅·테스트 설계 | High를 출발점으로 사용 |
| 복잡한 최적화·중대한 구조 판단·반복 미해결 오류 | Extra High 검토 |

실행 중 자동 조정은 공식 지원과 실제 권한이 있을 때만 한다. 그렇지 않으면 이유와 권장 수준을 알리고 사용자가 `/model` 또는 제공 UI에서 변경한다. 표시 이름으로 CLI ID를 추측하거나 전역 설정을 수정하지 않는다.

토큰의 평가 반영은 미확인이다. 정확성과 제한 시간 내 완성을 우선한다. 중복 파일 읽기·동일 검사 반복을 줄이되 보안·정합성·핵심 테스트는 생략하지 않는다. 실제 사용량이 제공되면 모델·추론 수준·작업·시간·토큰·결과를 기록한다. 데이터가 없으면 미측정으로 남기고 절약률을 만들지 않는다.

## 검증과 연습

저장소 루트에서 테스트한다.

```powershell
python -m unittest discover -s tests -v
```

연습 문제는 `practice/tasks/etch-schedule`과 `practice/tasks/pm-assign`이다. 풀이 세션에는 해당 문제 폴더만 제공한다. `practice/reference`는 평가자용이며 정답·기대값을 풀이 전에 노출하지 않는다.

`hx gate`는 등록된 요구사항과 기록된 증거의 기계적 검사다. 요구사항 등록 누락, 테스트 자체의 오류, UI 사용성, Cofa 제출 조건까지 보증하지 않는다. 최종 제출 전 원문·산출물·테스트·사용자 결정을 대조한다. 자동 시뮬레이션과 실제 사용자가 질문에 답한 연습은 별도로 보고한다.
