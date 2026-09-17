"""기술적 지표 계산 모듈.

이동평균, RSI, MACD, 볼린저밴드, 거래량 이동평균, 52주 신고가 대비 위치,
모멘텀을 계산합니다.

[look-ahead bias 방지 원칙]
모든 계산은 pandas의 rolling()/ewm()/shift(N, N>0) 처럼 "현재 시점(t)과 그
이전 데이터"만 사용하는 연산만 사용합니다. 즉 t 시점의 지표값을 계산할 때
t+1 이후의 미래 데이터가 절대 섞여 들어가지 않습니다.
"""
from __future__ import annotations

import pandas as pd

from . import config


def add_moving_averages(df: pd.DataFrame, windows=None) -> pd.DataFrame:
    windows = windows or config.MA_WINDOWS
    for w in windows:
        df[f"MA{w}"] = df["Close"].rolling(window=w, min_periods=w).mean()
    return df


def add_rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD) -> pd.DataFrame:
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    df[f"RSI{period}"] = rsi
    return df


def add_macd(
    df: pd.DataFrame,
    fast: int = config.MACD_FAST,
    slow: int = config.MACD_SLOW,
    signal: int = config.MACD_SIGNAL,
) -> pd.DataFrame:
    ema_fast = df["Close"].ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False, min_periods=slow).mean()

    df["MACD"] = ema_fast - ema_slow
    df["MACD_Signal"] = df["MACD"].ewm(span=signal, adjust=False, min_periods=signal).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]
    return df


def add_bollinger_bands(
    df: pd.DataFrame,
    window: int = config.BB_WINDOW,
    num_std: float = config.BB_NUM_STD,
) -> pd.DataFrame:
    mid = df["Close"].rolling(window=window, min_periods=window).mean()
    std = df["Close"].rolling(window=window, min_periods=window).std()

    df["BB_Mid"] = mid
    df["BB_Upper"] = mid + num_std * std
    df["BB_Lower"] = mid - num_std * std
    return df


def add_volume_ma(df: pd.DataFrame, window: int = config.VOLUME_MA_WINDOW) -> pd.DataFrame:
    df[f"Volume_MA{window}"] = df["Volume"].rolling(window=window, min_periods=window).mean()
    return df


def add_52w_high_ratio(df: pd.DataFrame, window: int = config.HIGH_52W_WINDOW) -> pd.DataFrame:
    """52주(약 252거래일) 최고 종가 대비 현재 종가의 비율을 계산합니다.

    Pct_Of_52W_High 가 0이면 현재가가 52주 신고가와 같다는 뜻이고,
    -0.1 이면 52주 신고가보다 10% 낮다는 뜻입니다.
    """
    rolling_high = df["Close"].rolling(window=window, min_periods=window).max()
    df["High52W"] = rolling_high
    df["Pct_Of_52W_High"] = df["Close"] / rolling_high - 1
    return df


def add_momentum(df: pd.DataFrame, windows=None) -> pd.DataFrame:
    windows = windows or config.MOMENTUM_WINDOWS
    for w in windows:
        df[f"Momentum{w}"] = df["Close"] / df["Close"].shift(w) - 1
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """위의 모든 지표를 한 번에 계산해서 붙여줍니다."""
    df = df.copy()
    df = add_moving_averages(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_volume_ma(df)
    df = add_52w_high_ratio(df)
    df = add_momentum(df)
    return df
