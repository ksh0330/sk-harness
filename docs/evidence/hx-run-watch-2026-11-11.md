# hx run 감시 범위·실제 정보 요청 보완

기록일: 2026-11-11 (KST). Windows·Python 3.12에서 수행한 준비 검증이다. 실제 Cofa·Linux 실행과 구분한다.

## 변경 범위

- `hx run`: 판정 규칙은 그대로 두고, `source_changed_during_run` 발생 시 실행 중 바뀐 감시 파일 경로와 `--watch` 수정 안내를 출력한다. 파일별 해시(`util.source_hashes`)를 추가했고 기존 fingerprint 계산 결과는 동일하다.
- hx-main 스킬·GUIDE: `--watch`는 실제 입력·코드만, 결과 파일·`data/*` 같은 넓은 패턴 금지. 요구사항별 체크포인트, 커밋 권한 승인은 정상 절차로 진행하고 불가하면 PLAN에 기록.
- 실제 정보: 이름·이메일·사번 등은 AI가 채우지 않고 사용자에게 요청한다. 공식 제출 값과 가짜 테스트 데이터를 구분하고 실제 값은 코드·기록·커밋에 남기지 않는다(hx-main·GUIDE·hx-ship·README).
- README: 복구 표 3행 추가, 이전에 미커밋이던 `cofa-final-*` 근거를 커밋해 깨진 링크를 복구.

## 확인한 근거

| 항목 | 결과 |
|---|---|
| 관련 회귀 | `test_audit_evidence test_ledger test_project test_collab` 60개 PASS, 284.112초 ([로그](hx-run-watch-tests.log)) |
| 신규 테스트 | 감시 범위 밖 결과 CSV/JSON 생성·덮어쓰기 PASS, 감시 입력 변경 FAIL과 경로 안내 출력 |
| CLI 재현 | 격리 폴더에서 `--watch` 없음 → FAIL+안내, 입력·코드만 감시 → 첫 실행·재실행 PASS, 입력 변경 → FAIL ([로그](hx-run-watch-cli.log)) |
| 미검증 | 실제 Cofa·Linux·Sol 6.1 모델이 새 지침대로 실제 정보를 요청하는지는 현장 확인 대상 |
