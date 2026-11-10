# 본선 운영 최종 보완 검증

기록일: 2026-11-11 (KST). Windows 새 노트북에서 수행한 준비 검증이다. 실제 Cofa 접속·Linux 실행·사람 참여와 구분한다.

## 변경 범위

- README 첫 화면을 현재 Cofa 작업 공간 기준의 두 줄 설정 → 정상 문구 → Codex → 메인 → 별도 중재 → 오류 복구 순서로 정리했다. 10가지 오류의 확인 사항·복구 문장과 쉬운 용어 설명을 추가했다.
- 기존 init에 한국어 `collab/LEARNING.md` 양식 생성만 추가했다. 기존 학습 기록은 덮어쓰지 않는다. 추가 의존성·설치 프로그램·프레임워크는 없다.
- 메인·중재·제출 지침과 PLAYBOOK에 실제 코드·장부·DM·검증 근거로 학습 기록을 유지·설명하는 절차를 연결했다. 서술형 AI·붙여넣기 금지가 적용되면 그 단계의 AI 도움을 중단한다.
- 별도 세션의 대화·컨텍스트·사용량 자동 공유와 추론 수준 자동 변경은 가정하지 않는다. 기본 훅 비활성·기존 지침 보존·사용자의 중요한 결정 권한을 유지한다.

## 확인한 근거

| 항목 | 결과·범위 |
|---|---|
| 변경 전 관련 테스트 | `python -B -m unittest discover -s tests -p test_project.py -v`: 13개 PASS, 84.687초. 초기화·Git·앱·스모크 포함 |
| 변경 후 관련 테스트 | `PYTHONPATH=tests python -B -m unittest test_project test_collab -v`: 32개 PASS, 309.563초. 설치·학습 기록 보존·잘못된 root/충돌·Git·장부·중재·단계·핸들러·제출 회귀 포함 |
| 격리 초기화 | TEMP 아래 공백 포함 과제 경로에서 doctor/init/status/req list, AGENTS와 네 스킬·GUIDE·BOARD·INBOX·LEARNING 생성, 기본 훅 파일 없음 |
| 기존 자료 보존 | 원문·README·AGENTS·CSV의 바이트 일치. 충돌 스킬·학습 기록 보존. 재초기화 후 직접 갱신한 학습 기록 유지 |
| 오류·경로 | `.hx`가 기존 일반 파일일 때 종료 2와 원본 보존. 파일을 root로 지정하는 오류는 단위 테스트로 확인. 잘못된 별도 폴더 초기화 후 실제 root로 재적용해도 기존 과제와 학습 기록 유지. 잘못 만든 폴더는 자동 삭제하지 않음 |
| Git·공유 | 격리 과제의 기준점·초기 분석 WIP 커밋, R1·미응답 Q1, PLAN·학습 기록, 중재 review/prompt 실제 실행. fixture 질문은 실제 사람·담당자 응답이 아님 |
| 중재 조회 | status·audit 전후 BOARD·PLAN·LEARNING·Git index 바이트 일치. review 등록은 별도 허용된 장부 쓰기 |
| CLI 인식 | Codex 0.165.0 `debug prompt-input`에서 AGENTS와 학습 지침 확인. 실제 app-server `skills/list`에서 네 hx 스킬 enabled=true |
| 실제 메인 모델 관찰 | 로컬 Astra High, 별도 독립 Git fixture에서 README 첫 프롬프트 실행. 스킬·GUIDE 읽기, hx 진단·상태·intake·profile, R1~R3·미응답 D1~D3·DM Q1 등록 확인. 240초 실행 한도로 계획·학습 갱신·WIP 커밋·최종 응답은 미완료. 모델 주도 전체 성공으로 세지 않음 |
| 스킬 검사기 | 번들 quick_validate.py 실행은 `ModuleNotFoundError: No module named 'yaml'`로 불가. 설치 없이 실제 CLI 파싱·발견을 별도로 확인. 검사기 PASS로 보고하지 않음 |
| Bash·Linux | README 기본 두 줄은 Git Bash `bash -n` 통과. WSL 배포판 없음, Docker/Podman 없음. 실제 Linux `/tmp/sk-harness` 실행은 미검증 |
| Cofa·훅 | 실제 Cofa 두 터미널·Sol 6.1 High 선택·추론 조절·신뢰 후 네이티브 훅은 미검증. 단위 테스트의 핸들러 호출은 네이티브 이벤트 증거가 아님 |

## 실행 기록

- [관련 회귀 테스트](cofa-final-tests.log)
- [격리 초기화·장부·Git·보존·오류·Bash 명령](cofa-final-commands.log)
- [실제 CLI 인식과 별도 모델 세션 관찰](cofa-final-runtime.json)
- [공개 전 민감정보·경로 검사](cofa-final-publication.json): GitHub 연결 도구로 `ksh0330/sk-harness`의 public·main·Clone URL 확인. 현재 텍스트와 도달 가능한 Git 이력의 일반 키·토큰 패턴 검사에서 실제 자격증명 탐지 없음. 기존 보안 검사의 명백한 합성 키 한 건은 원문을 검토해 테스트 데이터로 구분. 개인 ZIP·원본 세션·인증 파일은 포함하지 않음.

실행 스크립트·원본 프롬프트·원본 모델 이벤트는 Git 제외 `.audit-work/final`에만 보관한다. 준비 감사 fixture는 이전 `.audit-work/rehearsal`과 분리했다. 준비 저장소 자체·ex-harness에 init하지 않았으며 전역 설정·도구·신뢰를 변경하지 않았다.

Codex의 일반 스킬 탐색은 [공식 Skills 문서](https://learn.chatgpt.com/docs/build-skills), AGENTS 적용은 [공식 지침 문서](https://learn.chatgpt.com/docs/agent-configuration/agents-md), 모델·추론 선택은 [공식 CLI 문서](https://learn.chatgpt.com/docs/developer-commands?surface=cli)와 대조했다. 일반 지원은 실제 Cofa 제공·허용의 근거가 아니다.
