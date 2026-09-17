"""KOSPI/KOSDAQ 종목 목록과 개별 종목의 일봉(OHLCV) 데이터를 가져오는 모듈.

FinanceDataReader를 통해 데이터를 받아오고, 같은 데이터를 반복해서 매번
인터넷에서 새로 받지 않도록 data/raw/ 폴더에 CSV로 캐시합니다.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd

from . import config


def get_stock_list(force_refresh: bool = False) -> pd.DataFrame:
    """KOSPI + KOSDAQ 상장 종목 목록을 DataFrame으로 반환합니다.

    컬럼: Code(종목코드, 6자리 문자열), Name(종목명), Market(KOSPI/KOSDAQ)

    한 번 받아오면 data/raw/stock_list.csv 에 저장해두고, 이후에는 그 캐시를
    사용합니다. 최신 목록이 필요하면 force_refresh=True 로 호출하세요.
    """
    if config.STOCK_LIST_CACHE.exists() and not force_refresh:
        return pd.read_csv(config.STOCK_LIST_CACHE, dtype={"Code": str})

    kospi = fdr.StockListing("KOSPI")
    kospi["Market"] = "KOSPI"
    kosdaq = fdr.StockListing("KOSDAQ")
    kosdaq["Market"] = "KOSDAQ"

    stocks = pd.concat([kospi, kosdaq], ignore_index=True)

    # FinanceDataReader 버전에 따라 종목코드 컬럼 이름이 다를 수 있어 표준화합니다.
    if "Code" not in stocks.columns and "Symbol" in stocks.columns:
        stocks = stocks.rename(columns={"Symbol": "Code"})

    stocks["Code"] = stocks["Code"].astype(str).str.zfill(6)

    keep_cols = [c for c in ["Code", "Name", "Market", "Sector", "Industry"] if c in stocks.columns]
    stocks = stocks[keep_cols].drop_duplicates(subset="Code").reset_index(drop=True)
    stocks = stocks.sort_values(["Market", "Name"]).reset_index(drop=True)

    stocks.to_csv(config.STOCK_LIST_CACHE, index=False, encoding="utf-8-sig")
    return stocks


def _cache_path(ticker: str) -> Path:
    return config.RAW_DIR / f"{ticker}.csv"


def get_price_data(
    ticker: str,
    years: int = config.YEARS_OF_DATA,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """한 종목의 최근 N년 일봉(OHLCV) 데이터를 DataFrame으로 반환합니다.

    인덱스는 날짜(DatetimeIndex)이고, Open/High/Low/Close/Volume 컬럼을 가집니다.
    이미 받아둔 데이터가 있으면(캐시) 그것을 재사용하고, force_refresh=True 이면
    무조건 새로 받습니다.
    """
    cache_file = _cache_path(ticker)

    if cache_file.exists() and not force_refresh:
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        return df

    start_date = (dt.date.today() - dt.timedelta(days=365 * years + 30)).isoformat()
    df = fdr.DataReader(ticker, start_date)

    if df.empty:
        return df

    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.to_csv(cache_file)
    return df
