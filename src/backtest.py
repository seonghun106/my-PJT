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
from scipy import stats as scipy_stats

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


def _compute_baseline_returns(df: pd.DataFrame, horizons) -> dict:
    """시그널과 상관없이, 그냥 아무 날이나 샀다고 가정했을 때의 수익률 분포.

    시그널이 정말 의미가 있는지 판단하려면 "시그널 뜬 날의 수익률"을
    "아무 날의 수익률(baseline)"과 비교해봐야 합니다.
    """
    return {h: df[f"FwdReturn_{h}d"].dropna() for h in horizons}


def _confidence_label(n: int, pvalue: float) -> str:
    """표본 수와 p-value를 보고, 이 통계를 얼마나 신뢰할 수 있는지 한글 라벨로 요약합니다."""
    if n < config.MIN_SAMPLE_SIZE:
        return "표본부족"
    if pvalue is None or (isinstance(pvalue, float) and np.isnan(pvalue)):
        return "판정불가"
    if pvalue < config.PVALUE_SIGNIFICANT:
        return f"유의미(p<{config.PVALUE_SIGNIFICANT:g})"
    if pvalue < config.PVALUE_WEAK_SIGNIFICANT:
        return f"약한유의성(p<{config.PVALUE_WEAK_SIGNIFICANT:g})"
    return "유의성없음"


def _stats_for_mask(df: pd.DataFrame, mask: pd.Series, horizons, baseline: dict | None = None) -> dict:
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
            stats[f"net_mean_return_{h}d"] = np.nan
            stats[f"net_win_rate_{h}d"] = np.nan
            stats[f"baseline_mean_return_{h}d"] = np.nan
            stats[f"excess_return_{h}d"] = np.nan
            stats[f"pvalue_{h}d"] = np.nan
            stats[f"confidence_{h}d"] = "표본부족"
            continue

        mdds = df.loc[returns.index, mdd_col].dropna()
        net_returns = returns - config.ROUND_TRIP_COST_PCT  # 거래비용(수수료+세금 추정치) 차감

        stats[f"n_{h}d"] = int(len(returns))
        stats[f"mean_return_{h}d"] = float(returns.mean())
        stats[f"median_return_{h}d"] = float(returns.median())
        stats[f"win_rate_{h}d"] = float((returns > 0).mean())
        stats[f"prob_gain_10pct_{h}d"] = float((returns >= config.BIG_GAIN_THRESHOLD).mean())
        stats[f"avg_max_drawdown_{h}d"] = float(mdds.mean()) if len(mdds) else np.nan
        stats[f"net_mean_return_{h}d"] = float(net_returns.mean())
        stats[f"net_win_rate_{h}d"] = float((net_returns > 0).mean())

        baseline_returns = baseline.get(h) if baseline is not None else None
        if baseline_returns is not None and len(baseline_returns) >= 2 and len(returns) >= 2:
            _, pvalue = scipy_stats.ttest_ind(returns, baseline_returns, equal_var=False)
            stats[f"baseline_mean_return_{h}d"] = float(baseline_returns.mean())
            stats[f"excess_return_{h}d"] = float(returns.mean() - baseline_returns.mean())
            stats[f"pvalue_{h}d"] = float(pvalue)
        else:
            stats[f"baseline_mean_return_{h}d"] = np.nan
            stats[f"excess_return_{h}d"] = np.nan
            stats[f"pvalue_{h}d"] = np.nan

        stats[f"confidence_{h}d"] = _confidence_label(len(returns), stats[f"pvalue_{h}d"])

    return stats


def compute_signal_stats(
    df: pd.DataFrame,
    signal_cols,
    horizons=None,
    include_combinations: bool = True,
    max_combo_size: int = config.MAX_SIGNAL_COMBO_SIZE,
) -> pd.DataFrame:
    """시그널(및 시그널 조합)별로 발생 횟수와 이후 수익률 통계를 계산합니다.

    반환하는 DataFrame의 주요 컬럼 (h = 5, 20, 60 ...):
      signal, count,
      n_{h}d, mean_return_{h}d, median_return_{h}d, win_rate_{h}d,
      prob_gain_10pct_{h}d, avg_max_drawdown_{h}d,
      net_mean_return_{h}d, net_win_rate_{h}d          - 거래비용 차감 후 수익률/승률
      baseline_mean_return_{h}d                         - "아무 날"의 평균 수익률 (비교 기준)
      excess_return_{h}d                                - 시그널 평균수익률 - baseline 평균수익률
      pvalue_{h}d                                        - 시그널 수익률이 baseline과 통계적으로
                                                             다른지 검정한 p-value (작을수록 유의미)
      confidence_{h}d                                    - 표본수/p-value를 종합한 신뢰도 라벨
    """
    horizons = horizons or config.FORWARD_RETURN_HORIZONS
    baseline = _compute_baseline_returns(df, horizons)
    rows = []

    for col in signal_cols:
        stats = _stats_for_mask(df, df[col].fillna(False), horizons, baseline=baseline)
        stats["signal"] = col
        rows.append(stats)

    if include_combinations and max_combo_size >= 2:
        for size in range(2, max_combo_size + 1):
            for combo in combinations(signal_cols, size):
                mask = df[list(combo)].fillna(False).all(axis=1)
                if mask.sum() == 0:
                    continue
                stats = _stats_for_mask(df, mask, horizons, baseline=baseline)
                stats["signal"] = " & ".join(combo)
                rows.append(stats)

    stats_df = pd.DataFrame(rows)
    if stats_df.empty:
        return stats_df

    ordered_cols = ["signal", "count"] + [c for c in stats_df.columns if c not in ("signal", "count")]
    return stats_df[ordered_cols].sort_values("count", ascending=False).reset_index(drop=True)


def compute_signal_stats_by_regime(
    df: pd.DataFrame,
    signal_cols,
    horizons=None,
    regime_col: str = "market_uptrend",
) -> pd.DataFrame:
    """시장이 상승 추세일 때 / 하락 추세일 때로 나누어 시그널별 통계를 계산합니다.

    시장 전체가 오르고 있을 때 뜬 시그널과, 시장이 꺾인 상태에서 뜬 시그널은
    이후 성과가 다를 수 있어 구분해서 보는 것이 좋습니다.
    """
    horizons = horizons or config.FORWARD_RETURN_HORIZONS
    if regime_col not in df.columns:
        return pd.DataFrame()

    baseline = _compute_baseline_returns(df, horizons)
    rows = []

    for col in signal_cols:
        for label, regime_mask in [("상승장", df[regime_col] == True), ("하락장", df[regime_col] == False)]:  # noqa: E712
            mask = df[col].fillna(False) & regime_mask
            if mask.sum() == 0:
                continue
            stats = _stats_for_mask(df, mask, horizons, baseline=baseline)
            stats["signal"] = col
            stats["market_regime"] = label
            rows.append(stats)

    stats_df = pd.DataFrame(rows)
    if stats_df.empty:
        return stats_df

    ordered_cols = ["signal", "market_regime", "count"] + [
        c for c in stats_df.columns if c not in ("signal", "market_regime", "count")
    ]
    return stats_df[ordered_cols].sort_values(["signal", "market_regime"]).reset_index(drop=True)
