"""코스피/코스닥 지수 자체의 추세(상승장/하락장)를 판단하는 모듈.

같은 시그널이라도 시장 전체가 상승장일 때와 하락장일 때 성과가 크게 다를 수
있습니다. 이 모듈은 지수(KS11=코스피, KQ11=코스닥)의 200일 이동평균을 기준으로
"현재 시장이 상승 추세인지"를 판단해서, 종목별 시그널 통계를 상승장/하락장으로
나눠 볼 수 있게 해줍니다.
"""
from __future__ import annotations

import pandas as pd

from . import config, data_loader


def get_market_trend(
    market: str,
    years: int = config.YEARS_OF_DATA,
    ma_window: int = config.MARKET_TREND_MA_WINDOW,
) -> pd.Series:
    """market('KOSPI' 또는 'KOSDAQ')의 지수가 상승 추세인 날짜에 True인 Series를 반환합니다.

    판단 기준: 지수 종가가 자신의 N일(기본 200일) 이동평균보다 위에 있으면 상승 추세.
    """
    ticker = config.MARKET_INDEX_TICKERS.get(market, config.MARKET_INDEX_TICKERS["KOSPI"])
    df = data_loader.get_price_data(ticker, years=years)
    if df.empty:
        return pd.Series(dtype=bool)

    ma = df["Close"].rolling(window=ma_window, min_periods=ma_window).mean()
    uptrend = df["Close"] > ma
    uptrend.name = "market_uptrend"
    return uptrend


def attach_market_trend(df: pd.DataFrame, market: str, years: int = config.YEARS_OF_DATA) -> pd.DataFrame:
    """종목 DataFrame에 그 날짜의 시장 추세(상승장 여부) 컬럼을 붙여줍니다."""
    trend = get_market_trend(market, years=years)
    df = df.copy()
    if trend.empty:
        df["market_uptrend"] = False
    else:
        df["market_uptrend"] = trend.reindex(df.index, method="ffill").fillna(False)
    return df
