"""종목 하나를 받아서

  1) 가격 데이터 로딩 (data_loader)
  2) 기술적 지표 계산 (indicators)
  3) 시그널 계산 (signals)
  4) 미래 수익률 계산 (backtest)

를 한 번에 처리하는 파이프라인 함수. scripts/run_backtest.py 와 app.py가
공통으로 이 함수를 사용합니다.
"""
from __future__ import annotations

import pandas as pd

from . import backtest, config, data_loader, indicators, market_regime, signals


def build_stock_dataframe(
    ticker: str,
    market: str = "KOSPI",
    years: int = config.YEARS_OF_DATA,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """종목 코드 하나에 대해 지표 + 시그널 + 미래 수익률 + 시장 추세까지 계산된 DataFrame을 반환합니다.

    market은 'KOSPI' 또는 'KOSDAQ' — 이 종목이 속한 시장의 지수 추세(상승장/하락장)를
    같이 붙여서, 시장 상황별로 시그널 성과를 나눠볼 수 있게 합니다.

    데이터가 없거나 너무 짧으면(지표 워밍업 불가) 빈 DataFrame을 반환합니다.
    """
    df = data_loader.get_price_data(ticker, years=years, force_refresh=force_refresh)
    if df.empty or len(df) < config.MIN_HISTORY_DAYS:
        return pd.DataFrame()

    df = indicators.add_all_indicators(df)
    df = signals.add_all_signals(df)
    df = backtest.add_forward_returns(df)
    df = market_regime.attach_market_trend(df, market=market, years=years)
    return df


def build_screening_dataframe(
    ticker: str,
    years: int = config.YEARS_OF_DATA,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """종목 검색식(screener.py)용 가벼운 파이프라인: 시세 + 지표만 계산합니다.

    시장 전체(수백~수천 종목)를 훑어야 하는 검색식 화면에서는 속도가 중요하기 때문에,
    단일 종목 리서치에서만 필요한 시그널 백테스트·시장추세 결합 단계는 생략합니다.
    """
    df = data_loader.get_price_data(ticker, years=years, force_refresh=force_refresh)
    if df.empty or len(df) < config.MIN_HISTORY_DAYS:
        return pd.DataFrame()

    df = indicators.add_all_indicators(df)
    return df
