"""매매 시그널(신호) 정의 모듈.

각 시그널 함수는 True/False 값을 가진 pandas Series를 반환합니다.
(그 날짜에 시그널이 발생했으면 True)

[look-ahead bias 방지 원칙]
시그널 판정에는 t 시점까지 계산된 지표(indicators.py에서 만든, 이미
look-ahead가 없는 값들)만 사용합니다. 미래 종가나 미래 수익률은 시그널
판정에 절대 사용하지 않습니다. (미래 수익률은 backtest.py에서 "시그널이
발생한 뒤 실제로 어떻게 됐는지" 사후 평가용으로만 사용됩니다.)
"""
from __future__ import annotations

import pandas as pd

from . import config


def signal_golden_cross(
    df: pd.DataFrame,
    fast: int = config.SIGNAL_GOLDEN_CROSS_FAST,
    slow: int = config.SIGNAL_GOLDEN_CROSS_SLOW,
) -> pd.Series:
    """단기 이동평균이 장기 이동평균을 아래에서 위로 돌파(골든크로스)."""
    fast_ma = df[f"MA{fast}"]
    slow_ma = df[f"MA{slow}"]
    crossed_up = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    return crossed_up.fillna(False)


def signal_volume_spike(df: pd.DataFrame, multiplier: float = config.SIGNAL_VOLUME_MULTIPLIER) -> pd.Series:
    """거래량이 20일 평균 거래량의 multiplier배 이상."""
    vol_ma = df[f"Volume_MA{config.VOLUME_MA_WINDOW}"]
    spike = df["Volume"] >= multiplier * vol_ma
    return spike.fillna(False)


def signal_breakout_high(df: pd.DataFrame, window: int = config.SIGNAL_BREAKOUT_WINDOW) -> pd.Series:
    """최근 window거래일(오늘 제외) 최고 종가를 오늘 종가가 돌파."""
    prior_high = df["Close"].rolling(window=window, min_periods=window).max().shift(1)
    breakout = df["Close"] > prior_high
    return breakout.fillna(False)


def signal_rsi_cross_up(df: pd.DataFrame, threshold: float = config.SIGNAL_RSI_THRESHOLD) -> pd.Series:
    """RSI가 threshold를 아래에서 위로 돌파."""
    rsi_col = f"RSI{config.RSI_PERIOD}"
    rsi = df[rsi_col]
    crossed_up = (rsi > threshold) & (rsi.shift(1) <= threshold)
    return crossed_up.fillna(False)


# 시그널 이름 -> 계산 함수. 새 시그널을 추가하려면 함수를 만들고 여기에 등록만 하면
# backtest.py, app.py 등에서 자동으로 인식합니다.
SIGNAL_FUNCS = {
    "golden_cross_20_60": signal_golden_cross,
    "volume_spike_2x": signal_volume_spike,
    "breakout_60d_high": signal_breakout_high,
    "rsi_cross_up_50": signal_rsi_cross_up,
}

# 대시보드 등에서 사람이 읽기 좋은 한글 설명
SIGNAL_LABELS = {
    "golden_cross_20_60": "20일선이 60일선을 상향 돌파 (골든크로스)",
    "volume_spike_2x": "거래량이 20일 평균의 2배 이상",
    "breakout_60d_high": "최근 60거래일 신고가 돌파",
    "rsi_cross_up_50": "RSI가 50을 상향 돌파",
}


def add_all_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for name, func in SIGNAL_FUNCS.items():
        df[name] = func(df)
    return df


def get_signal_columns() -> list[str]:
    return list(SIGNAL_FUNCS.keys())
