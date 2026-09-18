"""기관/외국인 등 투자자별 순매수 거래대금 순위를 가져오는 모듈.

일반 시세(OHLCV)와 달리 "어떤 투자자(기관/외국인/개인)가 얼마나 순매수했는지"는
한국거래소(KRX)가 직접 제공하는 데이터라서, 이 프로젝트의 다른 부분(FinanceDataReader)과
달리 KRX 데이터를 직접 읽어오는 pykrx 라이브러리를 사용합니다.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from pykrx import stock as pykrx_stock

from . import config

# 화면에 보여줄 한글 라벨 -> pykrx가 요구하는 투자자 구분 문자열
INVESTOR_OPTIONS = {
    "기관": "기관합계",
    "외국인": "외국인",
    "개인": "개인",
}


def get_net_purchase_ranking(
    market: str = "KOSPI",
    investor: str = "기관",
    lookback_days: int = config.INVESTOR_FLOW_DEFAULT_DAYS,
    top_n: int = config.INVESTOR_FLOW_TOP_N,
) -> pd.DataFrame:
    """최근 lookback_days(달력일 기준) 동안 investor가 가장 많이 순매수한 종목을
    순매수거래대금 기준 상위 top_n개로 정렬해서 반환합니다.

    반환 컬럼: Code, Name, 순매수거래대금, 순매수거래량, 매수거래대금, 매도거래대금
    (거래대금 단위는 원)
    """
    investor_code = INVESTOR_OPTIONS.get(investor, investor)

    todate = dt.date.today()
    fromdate = todate - dt.timedelta(days=lookback_days)

    raw = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
        fromdate.strftime("%Y%m%d"), todate.strftime("%Y%m%d"), market, investor_code
    )
    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.reset_index().rename(
        columns={
            "티커": "Code",
            "종목명": "Name",
        }
    )
    df = df.sort_values("순매수거래대금", ascending=False).head(top_n).reset_index(drop=True)
    return df
