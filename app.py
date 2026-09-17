"""Stock Research Agent - Streamlit 대시보드

실행 방법 (프로젝트 루트 폴더에서):
    streamlit run app.py

자세한 설치/실행 방법은 README.md를 참고하세요.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src import backtest, config, data_loader, pipeline, signals

st.set_page_config(page_title="Stock Research Agent", page_icon="📈", layout="wide")


@st.cache_data(show_spinner="종목 목록을 불러오는 중...")
def load_stock_list() -> pd.DataFrame:
    return data_loader.get_stock_list()


@st.cache_data(show_spinner="가격 데이터를 불러오고 지표를 계산하는 중... (처음 조회하는 종목은 시간이 걸릴 수 있어요)")
def load_stock_data(ticker: str, years: int) -> pd.DataFrame:
    return pipeline.build_stock_dataframe(ticker, years=years)


def format_pct(x) -> str:
    return "-" if pd.isna(x) else f"{x:.2%}"


def main() -> None:
    st.title("📈 Stock Research Agent")
    st.caption("KOSPI/KOSDAQ 개인용 종목 리서치 도구 · 과거 시그널 통계는 참고용이며 투자 조언이 아닙니다.")

    stock_list = load_stock_list()

    with st.sidebar:
        st.header("🔍 종목 검색")

        market = st.selectbox("시장", ["전체", "KOSPI", "KOSDAQ"])
        filtered = stock_list if market == "전체" else stock_list[stock_list["Market"] == market]

        query = st.text_input("종목명 또는 코드로 검색", placeholder="예: 삼성전자 또는 005930")
        if query:
            filtered = filtered[
                filtered["Name"].str.contains(query, case=False, na=False)
                | filtered["Code"].str.contains(query, case=False, na=False)
            ]

        if filtered.empty:
            st.warning("검색 결과가 없습니다. 다른 검색어를 입력해보세요.")
            st.stop()

        filtered = filtered.head(200)  # 목록이 너무 길면 선택 박스가 느려지므로 상위 200개만 표시
        options = [f"{r.Name} ({r.Code})" for r in filtered.itertuples()]
        selected = st.selectbox(f"종목 선택 ({len(filtered)}개 표시)", options)
        ticker = selected.split("(")[-1].rstrip(")")
        name = selected.split(" (")[0]

        years = st.slider("불러올 데이터 기간(년)", min_value=1, max_value=5, value=config.YEARS_OF_DATA)

        st.markdown("---")
        st.caption("데이터 출처: FinanceDataReader (KRX/네이버 금융 등)")

    df = load_stock_data(ticker, years)
    if df.empty:
        st.error(
            "이 종목은 데이터가 충분하지 않아 지표를 계산할 수 없습니다. "
            "(상장한 지 얼마 안 됐거나, 거래정지 등의 이유일 수 있습니다) 다른 종목을 선택해주세요."
        )
        st.stop()

    latest = df.iloc[-1]
    prev_close = df["Close"].iloc[-2] if len(df) >= 2 else latest["Close"]

    st.subheader(f"{name} ({ticker})")
    metric_cols = st.columns(5)
    metric_cols[0].metric("현재가", f"{latest['Close']:,.0f}원", f"{(latest['Close'] / prev_close - 1):.2%}")
    metric_cols[1].metric("RSI(14)", f"{latest[f'RSI{config.RSI_PERIOD}']:.1f}")
    metric_cols[2].metric("52주 고점 대비", format_pct(latest["Pct_Of_52W_High"]))
    metric_cols[3].metric("20일 모멘텀", format_pct(latest["Momentum20"]))
    metric_cols[4].metric("60일 모멘텀", format_pct(latest["Momentum60"]))

    tab_chart, tab_signal, tab_stats = st.tabs(["📊 가격 차트 & 지표", "🚦 현재 시그널", "📈 과거 시그널 통계"])

    with tab_chart:
        render_price_chart(df)

    with tab_signal:
        render_current_signals(df)

    with tab_stats:
        render_signal_stats(df)


def render_price_chart(df: pd.DataFrame) -> None:
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.2, 0.25],
        vertical_spacing=0.04,
        subplot_titles=("가격 · 이동평균 · 볼린저밴드", "거래량", "RSI(14)"),
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="가격"
        ),
        row=1,
        col=1,
    )

    for w in config.MA_WINDOWS:
        fig.add_trace(go.Scatter(x=df.index, y=df[f"MA{w}"], name=f"MA{w}", line=dict(width=1)), row=1, col=1)

    fig.add_trace(
        go.Scatter(x=df.index, y=df["BB_Upper"], name="볼린저밴드 상단", line=dict(width=1, dash="dot")),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["BB_Lower"], name="볼린저밴드 하단", line=dict(width=1, dash="dot")),
        row=1,
        col=1,
    )

    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="거래량"), row=2, col=1)
    fig.add_trace(
        go.Scatter(x=df.index, y=df[f"Volume_MA{config.VOLUME_MA_WINDOW}"], name="거래량 20일 평균"),
        row=2,
        col=1,
    )

    fig.add_trace(go.Scatter(x=df.index, y=df[f"RSI{config.RSI_PERIOD}"], name="RSI14"), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="gray", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="gray", row=3, col=1)

    fig.update_layout(height=900, xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**MACD**")
    macd_fig = go.Figure()
    macd_fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD"))
    macd_fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], name="Signal"))
    macd_fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], name="Histogram"))
    macd_fig.update_layout(height=300, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(macd_fig, use_container_width=True)


def render_current_signals(df: pd.DataFrame) -> None:
    signal_cols = signals.get_signal_columns()
    latest = df.iloc[-1]
    active = [col for col in signal_cols if bool(latest[col])]

    if not active:
        st.info("가장 최근 거래일 기준으로 발생한 시그널이 없습니다.")
    else:
        st.success(f"가장 최근 거래일에 {len(active)}개의 시그널이 발생했습니다.")
        for col in active:
            st.markdown(f"- **{signals.SIGNAL_LABELS.get(col, col)}**")

    st.markdown("---")
    st.markdown("#### 최근 20거래일 시그널 발생 이력")
    recent = df.tail(20)[signal_cols].rename(columns=signals.SIGNAL_LABELS)
    st.dataframe(recent, use_container_width=True)


def render_signal_stats(df: pd.DataFrame) -> None:
    signal_cols = signals.get_signal_columns()

    st.markdown("#### 이 종목의 과거 시그널 통계")
    st.caption("이 종목의 지난 데이터에서 각 시그널(또는 조합)이 발생한 뒤 5/20/60거래일 후 수익률입니다.")

    stock_stats = backtest.compute_signal_stats(df, signal_cols)
    if stock_stats.empty:
        st.info("이 종목에서는 아직 발생한 시그널이 없습니다.")
    else:
        display_stats = stock_stats.copy()
        display_stats["signal"] = display_stats["signal"].map(
            lambda s: " & ".join(signals.SIGNAL_LABELS.get(part, part) for part in s.split(" & "))
        )
        display_stats = display_stats.rename(columns={"signal": "시그널", "count": "발생횟수"})
        st.dataframe(style_stats_table(display_stats), use_container_width=True)

    st.markdown("---")
    st.markdown("#### 전체 시장 기준 통계 (참고용)")
    market_stats_path = config.PROCESSED_DIR / "signal_stats.csv"
    if market_stats_path.exists():
        market_stats = pd.read_csv(market_stats_path)
        st.dataframe(style_stats_table(market_stats.rename(columns={"signal": "시그널", "count": "발생횟수"})), use_container_width=True)
    else:
        st.info(
            "아직 전체 시장 통계 파일이 없습니다. 터미널(명령 프롬프트)에서 아래 명령어를 실행하면 "
            "여러 종목을 한꺼번에 분석해서 전체 시장 기준 통계를 만들 수 있어요:\n\n"
            "```\npython scripts/run_backtest.py --market ALL --limit 100\n```"
        )


def style_stats_table(stats: pd.DataFrame):
    pct_keywords = ["return", "rate", "prob", "drawdown"]
    pct_cols = [c for c in stats.columns if any(k in c for k in pct_keywords)]
    return stats.style.format({c: "{:.2%}" for c in pct_cols}, na_rep="-")


if __name__ == "__main__":
    main()
