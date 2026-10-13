# semicycle

메모리 반도체 업황이 사이클의 어디쯤 있는지(회복·확장·둔화·수축)를 공개 통계로 매일 갱신해 보여주는 지표입니다.

> 업황의 위치를 보여줄 뿐, 주가 방향을 예측하거나 투자를 권유하지 않습니다.

## 무엇을 보여주나
- **수준**: 지금 업황이 과거 대비 얼마나 좋은가 (0–100)
- **방향**: 업황이 좋아지는 중인가 나빠지는 중인가 (0–100)
- **국면**: 수준·방향 각각 50을 기준으로 회복 / 확장 / 둔화 / 수축

가격·물량·재고·이익·수요 5개 필러, 11개 인자를 각자의 과거 이력 대비 백분위로 바꿔 가중 합산합니다.
인자 정의·가중치·발표 지연 가정은 [`indicators.yaml`](indicators.yaml) 한 곳에 있습니다.

## 데이터
한국은행 ECOS(메모리 수출물가지수), 관세청(집적회로 수출·장비 수입), 통계청 KOSIS(반도체 출하·재고지수),
FRED(미국 전자제품 주문·재고), SEC EDGAR(마이크론·하이퍼스케일러), OpenDART(SK하이닉스·삼성전자).

- 각 값은 실제 공개 시점 기준으로만 반영합니다(월간 통계는 발표 지연 가정, 분기 공시는 공시일).
- 새로 나타나거나 수정된 값은 `data/releases.csv`에 처음 본 날짜와 함께 기록됩니다.
- 매일 07:17(KST) GitHub Actions가 수집 → 점검 → 계산 → 사이트 배포를 실행합니다.
  한 소스가 실패하면 직전 데이터를 유지하고, 3일 넘게 실패하면 실행이 실패로 표시됩니다.

## 구조
```
indicators.yaml      인자·필러·가중치·출처 정의
semicycle/sources/   소스별 수집기
semicycle/           indicators(월별 패널) · score(백분위·국면) · validate · publish
run.py               전체 실행
data/                수집 원자료(long 포맷), releases.csv, status.json
site/                정적 사이트 (data/*.json은 실행 시 생성)
tests/               미래 정보 누수·분기 역산·점검 규칙 테스트
research/            설계·검증 기록(자동 실행 안 함)
```

## 로컬 실행
```
pip install -r requirements.txt
# .env 또는 환경변수: ECOS_API_KEY, DATA_GO_KR_KEY, KOSIS_API_KEY, DART_API_KEY, FRED_API_KEY, SEC_USER_AGENT("이름 / 이메일")
python run.py              # 수집부터 발행까지
python run.py --skip-fetch # 저장된 데이터로 계산만
python -m pytest -q tests
```
