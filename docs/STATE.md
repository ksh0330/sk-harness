# Codex 인수 및 안정화 상태

갱신: 2026-11-10 (KST). 진행 중.

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
