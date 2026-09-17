"""시그널 발생 이후의 미래 수익률을 계산하고, 시그널(또는 시그널 조합)별
통계를 집계하는 모듈.

[look-ahead bias 방지 원칙]
- 시그널 자체는 t 시점까지의 데이터로만 판정합니다 (signals.py).
- 여기서 계산하는 "미래 수익률(FwdReturn)"과 "보유기간 중 최대 낙폭
  (MaxDrawdown)"은 t 시점 이후 미래 데이터를 사용하는 값이 맞습니다. 하지만
  이 값들은 다른 지표나 시그널을 계산하는 데 절대 입력으로 쓰이지 않고,
  오직 "이 시그널이 과거에 발생했을 때 그 이후 실제로 어떻게 됐는가"를
  사후에 통계로 확인하기 위한 결과(label)로만 사용됩니다.
- 데이터의 끝부분처럼 미래 구간이 아직 존재하지 않는 날짜는 자동으로 NaN이
  되고, 통계 집계 시 제외됩니다.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from . import config


def _forward_min(close: pd.Series, horizon: int) -> pd.Series:
    """각 시점 t에 대해, t+1 ~ t+horizon 구간의 최저 종가를 반환합니다.

    (t 자신은 포함하지 않음 = 시그널 발생일 종가 대비 이후 낙폭을 보기 위함)
    """
    future_close = close.shift(-1)
    # 미래 방향으로의 rolling min을 구하기 위해 순서를 뒤집어서 rolling 후 다시 뒤집습니다.
    reversed_min = future_close[::-1].rolling(window=horizon, min_periods=horizon).min()[::-1]
    return reversed_min


def add_forward_returns(df: pd.DataFrame, horizons=None) -> pd.DataFrame:
    """각 시점 t 이후 N거래일 수익률과, 보유기간 중 최대 낙폭을 계산해 컬럼으로 추가합니다.

    - FwdReturn_{N}d: (t+N일 종가 / t일 종가) - 1
    - MaxDrawdown_{N}d: t일 종가 대비, t+1~t+N일 중 최저 종가로 계산한 최대 낙폭 (음수)
    """
    horizons = horizons or config.FORWARD_RETURN_HORIZONS
    df = df.copy()
    close = df["Close"]

    for h in horizons:
        future_close = close.shift(-h)
        df[f"FwdReturn_{h}d"] = future_close / close - 1

        min_close = _forward_min(close, h)
        df[f"MaxDrawdown_{h}d"] = min_close / close - 1

    return df


def _stats_for_mask(df: pd.DataFrame, mask: pd.Series, horizons) -> dict:
    stats = {"count": int(mask.sum())}

    for h in horizons:
        ret_col = f"FwdReturn_{h}d"
        mdd_col = f"MaxDrawdown_{h}d"

        returns = df.loc[mask, ret_col].dropna()

        if len(returns) == 0:
            stats[f"n_{h}d"] = 0
            stats[f"mean_return_{h}d"] = np.nan
            stats[f"median_return_{h}d"] = np.nan
            stats[f"win_rate_{h}d"] = np.nan
            stats[f"prob_gain_10pct_{h}d"] = np.nan
            stats[f"avg_max_drawdown_{h}d"] = np.nan
            continue

        mdds = df.loc[returns.index, mdd_col].dropna()

        stats[f"n_{h}d"] = int(len(returns))
        stats[f"mean_return_{h}d"] = float(returns.mean())
        stats[f"median_return_{h}d"] = float(returns.median())
        stats[f"win_rate_{h}d"] = float((returns > 0).mean())
        stats[f"prob_gain_10pct_{h}d"] = float((returns >= config.BIG_GAIN_THRESHOLD).mean())
        stats[f"avg_max_drawdown_{h}d"] = float(mdds.mean()) if len(mdds) else np.nan

    return stats


def compute_signal_stats(
    df: pd.DataFrame,
    signal_cols,
    horizons=None,
    include_combinations: bool = True,
    max_combo_size: int = config.MAX_SIGNAL_COMBO_SIZE,
) -> pd.DataFrame:
    """시그널(및 시그널 조합)별로 발생 횟수와 이후 수익률 통계를 계산합니다.

    반환하는 DataFrame의 컬럼:
      signal, count,
      n_{h}d, mean_return_{h}d, median_return_{h}d, win_rate_{h}d,
      prob_gain_10pct_{h}d, avg_max_drawdown_{h}d  (h = 5, 20, 60 ...)
    """
    horizons = horizons or config.FORWARD_RETURN_HORIZONS
    rows = []

    for col in signal_cols:
        stats = _stats_for_mask(df, df[col].fillna(False), horizons)
        stats["signal"] = col
        rows.append(stats)

    if include_combinations and max_combo_size >= 2:
        for size in range(2, max_combo_size + 1):
            for combo in combinations(signal_cols, size):
                mask = df[list(combo)].fillna(False).all(axis=1)
                if mask.sum() == 0:
                    continue
                stats = _stats_for_mask(df, mask, horizons)
                stats["signal"] = " & ".join(combo)
                rows.append(stats)

    stats_df = pd.DataFrame(rows)
    if stats_df.empty:
        return stats_df

    ordered_cols = ["signal", "count"] + [c for c in stats_df.columns if c not in ("signal", "count")]
    return stats_df[ordered_cols].sort_values("count", ascending=False).reset_index(drop=True)
