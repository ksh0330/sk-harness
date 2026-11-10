# 연습 과제: 식각 공정 LOT 투입 계획 (가상 데이터)

> 본선 문제가 아니다. hx와 에이전트를 함께 쓰는 흐름을 30분 안에 한 번 돌려 보기 위한 연습용이다.

## 배경

식각(Etch) 공정 앞에 대기 중인 lot들을 설비에 배정하고 시작 시각을 정해야 한다. 현재는 담당자가 엑셀에서 수작업으로 순서를 정하며, 긴급 lot의 납기 지연이 반복되고 있다.

## 입력

- `data/lots.csv`: `lot_id`, `product`, `proc_min`(처리 시간, 분), `due_min`(납기, 기준 시각 0부터의 분), `priority`(1 긴급, 2 보통, 3 낮음), `eligible`(투입 가능한 설비, `|`로 구분)
- `data/equipment.csv`: `eqp_id`, `available_from_min`(이 시각부터 사용 가능)

## 출력

- `out/schedule.csv`: `lot_id`, `eqp_id`, `start_min`, `end_min`
- `out/rejected.csv`: `lot_id`, `reason` (계획에서 제외한 lot과 그 이유)

실행 방법은 `python scheduler.py data out` 한 줄이어야 한다.

## 규칙

1. 모든 lot은 schedule 또는 rejected 중 정확히 한 곳에 한 번만 나온다.
2. lot은 `eligible`에 적힌 설비에만 배정한다.
3. 한 설비에서 두 lot의 작업 시간이 겹치지 않는다.
4. `start_min`은 그 설비의 `available_from_min` 이상이고, `end_min = start_min + proc_min`이다.
5. 데이터 오류가 있는 lot(처리 시간이 없음, 투입 가능한 설비가 설비 목록에 하나도 없음)은 제외하고 이유를 남긴다. 완전히 같은 행이 중복되면 한 번만 처리한다.

## 평가

가중 납기 지연 합 TWT = Σ weight × max(0, `end_min` − `due_min`). weight는 priority 1 → 3, 2 → 2, 3 → 1. 낮을수록 좋다. 규칙을 하나라도 어기면 점수와 무관하게 실격이다.
