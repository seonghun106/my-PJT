"""프로젝트 전역 설정값.

경로, 지표 계산 파라미터, 시그널 임계값 등을 한 곳에 모아둡니다.
값을 바꾸고 싶으면 이 파일만 수정하면 됩니다.
"""
from __future__ import annotations

from pathlib import Path

# 프로젝트 최상위 폴더 (이 파일 기준으로 두 단계 위: src/config.py -> src -> 프로젝트 루트)
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

STOCK_LIST_CACHE = RAW_DIR / "stock_list.csv"

# 몇 년치 일봉 데이터를 받을지
YEARS_OF_DATA = 5

# 최소한 이 정도 거래일 데이터가 있어야 지표/시그널을 계산합니다.
# (200일 이동평균, 52주 신고가 등 긴 지표들이 워밍업되려면 최소한의 데이터가 필요합니다)
MIN_HISTORY_DAYS = 260

# 이동평균 윈도우 (일)
MA_WINDOWS = [5, 20, 60, 120, 200]

# RSI
RSI_PERIOD = 14

# MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# 볼린저 밴드
BB_WINDOW = 20
BB_NUM_STD = 2

# 거래량 이동평균
VOLUME_MA_WINDOW = 20

# 52주 신고가 (거래일 기준 약 1년 = 252일)
HIGH_52W_WINDOW = 252

# 모멘텀 (N일 전 대비 수익률)
MOMENTUM_WINDOWS = [20, 60]

# 시그널 발생 후 이후 수익률을 측정할 기간 (거래일)
FORWARD_RETURN_HORIZONS = [5, 20, 60]

# 시그널 파라미터
SIGNAL_BREAKOUT_WINDOW = 60          # N거래일 신고가 돌파
SIGNAL_VOLUME_MULTIPLIER = 2.0       # 거래량이 20일 평균의 몇 배 이상이면 시그널인지
SIGNAL_RSI_THRESHOLD = 50            # RSI가 이 값을 상향 돌파하면 시그널
SIGNAL_GOLDEN_CROSS_FAST = 20
SIGNAL_GOLDEN_CROSS_SLOW = 60

# 통계에서 "크게 상승"으로 볼 기준 수익률
BIG_GAIN_THRESHOLD = 0.10

# 시그널 조합 통계를 만들 때 몇 개까지 묶어서 볼지 (3 = 최대 세 개까지 동시 충족 조합도 확인)
MAX_SIGNAL_COMBO_SIZE = 3

# 이보다 발생 횟수가 적으면 "표본 부족"으로 표시합니다 (통계를 신뢰하기 어려운 수준).
MIN_SAMPLE_SIZE = 30

# 시그널 발생 후 수익률이 "그냥 아무 날"(baseline)과 통계적으로 다른지 검정할 때
# 사용하는 유의수준 기준값들 (p-value 해석용)
PVALUE_SIGNIFICANT = 0.05
PVALUE_WEAK_SIGNIFICANT = 0.10

# 왕복 거래비용 대략치 (매수+매도 수수료 + 증권거래세 포함, 1회 매매 기준 추정치).
# 실제 비용은 증권사/세율 변경에 따라 다르므로 참고용 추정값입니다.
ROUND_TRIP_COST_PCT = 0.003  # 0.3%

# 시장 추세 판단에 쓰는 지수 티커 (코스피/코스닥 지수)와 추세 판단 이동평균 기간
MARKET_INDEX_TICKERS = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}
MARKET_TREND_MA_WINDOW = 200
