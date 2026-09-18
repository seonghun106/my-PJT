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

# 거래량 이동평균 (단기/장기 - 장기는 "평소 거래량"을 판단할 때 사용)
VOLUME_MA_WINDOW = 20
VOLUME_MA_LONG_WINDOW = 60

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

# ── 종목 검색식(스크리너) 파라미터 ──────────────────────────────────────────
# "지금 이 조건을 만족하는 종목"을 시장 전체에서 찾는 검색식들의 설정값입니다.

# 월봉 이동평균 돌파 검색식
MONTHLY_MA_WINDOW = 10                    # 월봉 몇 개월선을 볼지
MONTHLY_BREAKOUT_LOOKBACK_MONTHS = 12      # "과거 몇 개월 동안 못 넘었는지" 확인할 기간
MONTHLY_BREAKOUT_VOLUME_MULTIPLIER = 2.5   # 돌파월 거래량이 이전 평균의 몇 배 이상이어야 하는지

# 정배열 / 이격도
DISPARITY_OVERBOUGHT = 115.0   # 20일 이격도(종가/20일선*100)가 이 값 이상이면 "과열"
DISPARITY_OVERSOLD = 88.0      # 이 값 이하이면 "침체"

# 눌림목 매수: 상승추세(종가>60일선, 20일선>60일선) 중 20일선을 딛고 반등

# 박스권 돌파
BOX_BREAKOUT_WINDOW = 20            # 박스권으로 볼 과거 거래일 수 (오늘 제외)
BOX_RANGE_PCT = 0.10                # 이 비율 이하로 좁게 움직였으면 "박스권"으로 인정
BOX_BREAKOUT_VOLUME_MULTIPLIER = 1.5  # 돌파 당일 거래량이 20일 평균의 몇 배 이상이어야 하는지

# 거래량 바닥 다지기 후 급증 (매집 후 발화)
VOLUME_DRYUP_RATIO = 0.6          # 20일 평균거래량이 60일 평균거래량의 이 비율 이하면 "거래 한산"
VOLUME_SPIKE_MULTIPLIER_SCREEN = 3.0  # 오늘 거래량이 20일 평균의 몇 배 이상이면 "급증"

# 한 번에 스캔할 기본/최대 종목 수 (너무 많으면 웹 화면에서 느려집니다)
SCREENER_DEFAULT_LIMIT = 100
SCREENER_MAX_LIMIT = 300

# 투자자별(기관/외국인) 순매수 거래대금 조회 시 기본 조회 기간(일)과 노출 종목 수
INVESTOR_FLOW_DEFAULT_DAYS = 20
INVESTOR_FLOW_TOP_N = 30
