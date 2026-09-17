#!/usr/bin/env python3
"""KOSPI/KOSDAQ 종목들을 대상으로 시그널을 계산하고, 시그널(및 조합)별
과거 성과 통계를 CSV로 저장하는 배치 스크립트.

실행 예시 (프로젝트 루트 폴더에서 실행하세요):

    # 테스트로 KOSPI 30종목만 빠르게 돌려보기
    python scripts/run_backtest.py --market KOSPI --limit 30

    # 전체 종목 대상으로 실행 (시간이 꽤 걸립니다, 종목당 몇 초 소요)
    python scripts/run_backtest.py --market ALL

결과물:
    data/processed/signal_stats.csv   - 시그널(조합)별 통계
    data/processed/signal_events.csv  - 종목/날짜별 시그널 발생 이력 (이후 수익률 포함)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가해서 'src' 패키지를 어디서 실행해도 찾을 수 있게 합니다.
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from tqdm import tqdm

from src import backtest, config, data_loader, pipeline, signals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KOSPI/KOSDAQ 시그널 백테스트")
    parser.add_argument("--market", choices=["KOSPI", "KOSDAQ", "ALL"], default="ALL", help="대상 시장")
    parser.add_argument("--limit", type=int, default=None, help="테스트할 종목 수를 제한합니다 (전체 실행은 오래 걸립니다)")
    parser.add_argument("--years", type=int, default=config.YEARS_OF_DATA, help="몇 년치 데이터를 사용할지")
    parser.add_argument("--refresh", action="store_true", help="캐시된 가격 데이터를 무시하고 다시 받습니다")
    parser.add_argument("--out", default=str(config.PROCESSED_DIR / "signal_stats.csv"), help="시그널 통계 CSV 저장 경로")
    parser.add_argument(
        "--events-out",
        default=str(config.PROCESSED_DIR / "signal_events.csv"),
        help="개별 시그널 발생 이력 CSV 저장 경로",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    stocks = data_loader.get_stock_list()
    if args.market != "ALL":
        stocks = stocks[stocks["Market"] == args.market]
    if args.limit:
        stocks = stocks.head(args.limit)

    print(f"대상 종목 수: {len(stocks)}")

    signal_cols = signals.get_signal_columns()
    all_frames = []

    for row in tqdm(list(stocks.itertuples()), desc="종목별 데이터 처리"):
        ticker, name = row.Code, row.Name
        try:
            df = pipeline.build_stock_dataframe(ticker, years=args.years, force_refresh=args.refresh)
        except Exception as exc:  # 개별 종목 실패는 건너뛰고 계속 진행합니다.
            print(f"[경고] {ticker} {name} 처리 실패: {exc}")
            continue

        if df.empty:
            continue

        df = df.copy()
        df["Code"] = ticker
        df["Name"] = name
        all_frames.append(df)

    if not all_frames:
        print("처리된 데이터가 없습니다. 네트워크 연결이나 종목 코드를 확인해주세요.")
        return

    combined = pd.concat(all_frames, axis=0)

    print("시그널 통계 계산 중...")
    stats = backtest.compute_signal_stats(combined, signal_cols)
    stats.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[완료] 시그널 통계 저장: {args.out} ({len(stats)}행)")

    event_cols = ["Code", "Name", "Close"] + signal_cols + [f"FwdReturn_{h}d" for h in config.FORWARD_RETURN_HORIZONS]
    events = combined[event_cols].copy()
    events = events[events[signal_cols].any(axis=1)]
    events.index.name = "Date"
    events = events.reset_index()
    events.to_csv(args.events_out, index=False, encoding="utf-8-sig")
    print(f"[완료] 시그널 발생 이력 저장: {args.events_out} ({len(events)}행)")


if __name__ == "__main__":
    main()
