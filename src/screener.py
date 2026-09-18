"""시장 전체를 대상으로 "지금 이 조건을 만족하는 종목"을 찾는 종목 검색식(스크리너) 모음.

signals.py의 시그널이 "과거의 각 날짜마다 시그널이 떴었는가"를 판정해서 나중에
통계(backtest.py)를 내는 데 쓰인다면, 여기 있는 검색식들은 HTS/MTS의 '조건검색식'처럼
"가장 최근 거래일 기준으로 조건을 만족하는가"만 판정합니다. 그래서 시장 전체(수백~수천
종목)를 훑어서 지금 조건에 맞는 종목 목록을 뽑아내는 용도로 씁니다.

각 함수는 종목 하나의 지표 계산이 끝난 DataFrame(indicators.add_all_indicators 결과)을
받아서, 조건을 만족하면 관련 수치가 담긴 dict를, 만족하지 않으면 None을 반환합니다.
"""
from __future__ import annotations

import pandas as pd

from . import config


def _monthly_resample(df: pd.DataFrame) -> pd.DataFrame:
    """일봉 데이터를 월봉(월별 마지막 종가, 월별 거래량 합계)으로 바꿉니다.

    가장 마지막 달(이번 달)은 거래일이 아직 다 지나지 않았을 수 있는데, 그 경우 지금까지의
    데이터만으로 "진행 중인 이번 달 종가"를 만듭니다 (실시간 검색식이 흔히 쓰는 방식입니다).
    """
    monthly = pd.DataFrame(
        {
            "Close": df["Close"].resample("ME").last(),
            "Volume": df["Volume"].resample("ME").sum(),
        }
    )
    return monthly.dropna(subset=["Close"])


def screen_monthly_ma_breakout(
    df: pd.DataFrame,
    ma_window: int = config.MONTHLY_MA_WINDOW,
    lookback_months: int = config.MONTHLY_BREAKOUT_LOOKBACK_MONTHS,
    volume_multiplier: float = config.MONTHLY_BREAKOUT_VOLUME_MULTIPLIER,
) -> dict | None:
    """월봉 M개월선을 과거 lookback_months 동안 넘지 못하다가, 지난달에 막 넘어서
    이번 달에도 그 위에 안착해 있는지 확인합니다. 돌파한 달의 거래량도 그 이전
    평균보다 충분히(volume_multiplier배 이상) 늘어나야 합니다.
    """
    monthly = _monthly_resample(df)
    if monthly.empty:
        return None

    monthly = monthly.copy()
    monthly["MA"] = monthly["Close"].rolling(window=ma_window, min_periods=ma_window).mean()

    need = lookback_months + 2  # 과거 lookback개월 + 돌파월(지난달) + 이번달
    if len(monthly) < need:
        return None

    recent = monthly.iloc[-need:]
    past_months = recent.iloc[:lookback_months]
    breakout_month = recent.iloc[lookback_months]
    current_month = recent.iloc[lookback_months + 1]

    if past_months["MA"].isna().any() or pd.isna(breakout_month["MA"]) or pd.isna(current_month["MA"]):
        return None

    was_below_before = bool((past_months["Close"] < past_months["MA"]).all())
    broke_out_last_month = bool(breakout_month["Close"] >= breakout_month["MA"])
    still_above_now = bool(current_month["Close"] >= current_month["MA"])

    prior_avg_volume = float(past_months["Volume"].mean())
    volume_ok = prior_avg_volume > 0 and breakout_month["Volume"] >= volume_multiplier * prior_avg_volume

    if was_below_before and broke_out_last_month and still_above_now and volume_ok:
        return {
            "돌파월": breakout_month.name.strftime("%Y-%m"),
            "돌파월_거래량배수": float(breakout_month["Volume"] / prior_avg_volume),
            "이번달_이평선대비": float(current_month["Close"] / current_month["MA"] - 1),
        }
    return None


def screen_ma_alignment(df: pd.DataFrame) -> dict | None:
    """정배열(단기 이동평균이 장기 이동평균보다 위) 상태인 종목을 찾습니다."""
    if len(df) < 2:
        return None
    latest, prev = df.iloc[-1], df.iloc[-2]

    aligned_now = latest["MA5"] > latest["MA20"] > latest["MA60"] > latest["MA120"]
    if not bool(aligned_now):
        return None

    aligned_before = prev["MA5"] > prev["MA20"] > prev["MA60"] > prev["MA120"]
    return {"신규전환": bool(not aligned_before)}


def screen_pullback_rebound(df: pd.DataFrame) -> dict | None:
    """상승추세(종가>60일선, 20일선>60일선)를 유지한 채 20일선까지 눌렸다가 다시
    20일선 위로 반등한 종목을 찾습니다 ("눌림목 매수")."""
    if len(df) < 2:
        return None
    latest, prev = df.iloc[-1], df.iloc[-2]

    cond = (
        latest["Close"] > latest["MA20"]
        and prev["Close"] <= prev["MA20"]
        and latest["Close"] > latest["MA60"]
        and latest["MA20"] > latest["MA60"]
    )
    if not bool(cond):
        return None
    return {"MA20_이격도": float(latest["Close"] / latest["MA20"] - 1)}


def screen_disparity(
    df: pd.DataFrame,
    overbought: float = config.DISPARITY_OVERBOUGHT,
    oversold: float = config.DISPARITY_OVERSOLD,
) -> dict | None:
    """20일 이격도(종가/20일선*100)가 과열 또는 침체 구간에 들어선 종목을 찾습니다."""
    latest = df.iloc[-1]
    if pd.isna(latest["MA20"]) or latest["MA20"] == 0:
        return None

    disparity = float(latest["Close"] / latest["MA20"] * 100)
    if disparity >= overbought:
        return {"이격도": disparity, "구분": "과열"}
    if disparity <= oversold:
        return {"이격도": disparity, "구분": "침체"}
    return None


def screen_box_breakout(
    df: pd.DataFrame,
    box_window: int = config.BOX_BREAKOUT_WINDOW,
    box_range_pct: float = config.BOX_RANGE_PCT,
    volume_multiplier: float = config.BOX_BREAKOUT_VOLUME_MULTIPLIER,
) -> dict | None:
    """좁은 박스권(box_window일 동안 변동폭 box_range_pct 이내)에서 횡보하다가,
    거래량을 동반하며 박스 상단을 오늘 돌파한 종목을 찾습니다."""
    if len(df) < box_window + 1:
        return None

    recent = df.iloc[-(box_window + 1) : -1]  # 오늘을 제외한 과거 box_window일
    box_high = recent["Close"].max()
    box_low = recent["Close"].min()
    if pd.isna(box_high) or pd.isna(box_low) or box_low <= 0:
        return None

    box_pct = (box_high - box_low) / box_low
    latest = df.iloc[-1]
    vol_ma_col = f"Volume_MA{config.VOLUME_MA_WINDOW}"

    cond = (
        box_pct <= box_range_pct
        and latest["Close"] > box_high
        and not pd.isna(latest[vol_ma_col])
        and latest["Volume"] >= volume_multiplier * latest[vol_ma_col]
    )
    if not bool(cond):
        return None
    return {"박스폭": float(box_pct), "돌파율": float(latest["Close"] / box_high - 1)}


def screen_volume_dryup_spike(
    df: pd.DataFrame,
    dryup_ratio: float = config.VOLUME_DRYUP_RATIO,
    spike_multiplier: float = config.VOLUME_SPIKE_MULTIPLIER_SCREEN,
) -> dict | None:
    """한동안 거래량이 눈에 띄게 줄어(매집 구간) 있다가, 오늘 갑자기 거래량이 터지면서
    주가도 오른 종목을 찾습니다 ("거래량 바닥 다지기 후 급증")."""
    if len(df) < 2:
        return None
    latest, prev = df.iloc[-1], df.iloc[-2]

    vol_ma_short_col = f"Volume_MA{config.VOLUME_MA_WINDOW}"
    vol_ma_long_col = f"Volume_MA{config.VOLUME_MA_LONG_WINDOW}"

    vol_ma_short_prev = prev[vol_ma_short_col]
    vol_ma_long_prev = prev[vol_ma_long_col]
    if pd.isna(vol_ma_short_prev) or pd.isna(vol_ma_long_prev) or vol_ma_long_prev == 0:
        return None

    was_dry = vol_ma_short_prev <= dryup_ratio * vol_ma_long_prev
    if not was_dry or pd.isna(latest[vol_ma_short_col]) or latest[vol_ma_short_col] == 0:
        return None

    spiked = latest["Volume"] >= spike_multiplier * latest[vol_ma_short_col]
    price_up = latest["Close"] > prev["Close"]
    if not (spiked and price_up):
        return None

    return {"거래량배수": float(latest["Volume"] / latest[vol_ma_short_col])}


SCREENER_FUNCS = {
    "monthly_ma_breakout": screen_monthly_ma_breakout,
    "ma_alignment": screen_ma_alignment,
    "pullback_rebound": screen_pullback_rebound,
    "disparity": screen_disparity,
    "box_breakout": screen_box_breakout,
    "volume_dryup_spike": screen_volume_dryup_spike,
}

SCREENER_LABELS = {
    "monthly_ma_breakout": f"월봉 {config.MONTHLY_MA_WINDOW}선 돌파 후 안착",
    "ma_alignment": "정배열 종목",
    "pullback_rebound": "눌림목 매수 (20일선 지지 후 반등)",
    "disparity": "이격도 과열/침체",
    "box_breakout": "박스권 돌파",
    "volume_dryup_spike": "거래량 바닥 다지기 후 급증",
}

SCREENER_DESCRIPTIONS = {
    "monthly_ma_breakout": (
        f"최근 {config.MONTHLY_BREAKOUT_LOOKBACK_MONTHS}개월간 월봉 "
        f"{config.MONTHLY_MA_WINDOW}선을 넘지 못하다가, 지난달 거래량을 동반하며 돌파한 뒤 "
        "이번 달에도 그 위에 머물러 있는 종목"
    ),
    "ma_alignment": "5일선 > 20일선 > 60일선 > 120일선 순서로 정렬된(정배열) 종목",
    "pullback_rebound": "상승추세를 유지한 채 20일선까지 눌렸다가 다시 20일선 위로 반등한 종목",
    "disparity": "종가가 20일선보다 지나치게 높거나(과열) 낮은(침체) 종목",
    "box_breakout": "좁은 박스권에서 횡보하다 거래량을 동반해 박스 상단을 돌파한 종목",
    "volume_dryup_spike": "거래량이 한동안 잠잠하다가 갑자기 터지면서 주가도 오른 종목",
}


def get_screener_names() -> list[str]:
    return list(SCREENER_FUNCS.keys())
