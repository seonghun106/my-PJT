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
def load_stock_data(ticker: str, stock_market: str, years: int) -> pd.DataFrame:
    return pipeline.build_stock_dataframe(ticker, market=stock_market, years=years)


def format_pct(x) -> str:
    return "-" if pd.isna(x) else f"{x:.2%}"


def main() -> None:
    st.title("📈 Stock Research Agent")
    st.caption("KOSPI/KOSDAQ 개인용 종목 리서치 도구 · 과거 시그널 통계는 참고용이며 투자 조언이 아닙니다.")

    stock_list = load_stock_list()

    with st.sidebar:
        st.header("🔍 종목 검색")

        market_filter = st.selectbox("시장", ["전체", "KOSPI", "KOSDAQ"])
        filtered = stock_list if market_filter == "전체" else stock_list[stock_list["Market"] == market_filter]

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
        stock_market = filtered.loc[filtered["Code"] == ticker, "Market"].iloc[0]

        years = st.slider("불러올 데이터 기간(년)", min_value=1, max_value=5, value=config.YEARS_OF_DATA)

        st.markdown("---")
        st.caption("데이터 출처: FinanceDataReader (KRX/네이버 금융 등)")

    df = load_stock_data(ticker, stock_market, years)
    if df.empty:
        st.error(
            "이 종목은 데이터가 충분하지 않아 지표를 계산할 수 없습니다. "
            "(상장한 지 얼마 안 됐거나, 거래정지 등의 이유일 수 있습니다) 다른 종목을 선택해주세요."
        )
        st.stop()

    latest = df.iloc[-1]
    prev_close = df["Close"].iloc[-2] if len(df) >= 2 else latest["Close"]

    st.subheader(f"{name} ({ticker})")
    metric_cols = st.columns(6)
    metric_cols[0].metric("현재가", f"{latest['Close']:,.0f}원", f"{(latest['Close'] / prev_close - 1):.2%}")
    metric_cols[1].metric("RSI(14)", f"{latest[f'RSI{config.RSI_PERIOD}']:.1f}")
    metric_cols[2].metric("52주 고점 대비", format_pct(latest["Pct_Of_52W_High"]))
    metric_cols[3].metric("20일 모멘텀", format_pct(latest["Momentum20"]))
    metric_cols[4].metric("60일 모멘텀", format_pct(latest["Momentum60"]))
    metric_cols[5].metric(f"{stock_market} 지수 추세", "상승장" if bool(latest["market_uptrend"]) else "하락장")

    tab_chart, tab_signal, tab_stats = st.tabs(["📊 가격 차트 & 지표", "🚦 현재 시그널", "📈 과거 시그널 통계"])

    with tab_chart:
        render_price_chart(df)

    with tab_signal:
        render_current_signals(df)

    with tab_stats:
        render_signal_stats(df)


DEFAULT_ZOOM_DAYS = 126  # 처음 열었을 때 보여줄 기간 (약 6개월치 거래일). 슬라이더/버튼으로 더 넓게 볼 수 있음.


def render_price_chart(df: pd.DataFrame) -> None:
    st.caption(
        "📱 손가락 두 개로 오므리고 벌리면 확대/축소, 한 손가락으로 드래그하면 이동합니다. "
        "위쪽 기간 버튼(1개월/3개월/6개월/1년/전체)이나 맨 아래 슬라이더로도 조절할 수 있어요."
    )

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.42, 0.14, 0.19, 0.25],
        vertical_spacing=0.03,
        subplot_titles=("가격 · 이동평균 · 볼린저밴드", "거래량", "RSI(14)", "MACD"),
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name="가격", increasing_line_color="#d62728", decreasing_line_color="#1f77b4",
        ),
        row=1,
        col=1,
    )

    # MA5/20/60은 기본으로 보여주고, 120/200은 범례를 눌러야 나타나게 해서 처음 화면을 덜 복잡하게 만듭니다.
    default_visible_ma = {5, 20, 60}
    for w in config.MA_WINDOWS:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df[f"MA{w}"], name=f"MA{w}", line=dict(width=1),
                visible=True if w in default_visible_ma else "legendonly",
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["BB_Upper"], name="볼린저밴드 상단", line=dict(width=1, dash="dot"), visible="legendonly"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["BB_Lower"], name="볼린저밴드 하단", line=dict(width=1, dash="dot"), visible="legendonly"),
        row=1,
        col=1,
    )

    volume_colors = ["#d62728" if c >= o else "#1f77b4" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="거래량", marker_color=volume_colors), row=2, col=1)
    fig.add_trace(
        go.Scatter(x=df.index, y=df[f"Volume_MA{config.VOLUME_MA_WINDOW}"], name="거래량 20일 평균", line=dict(width=1)),
        row=2,
        col=1,
    )

    fig.add_trace(go.Scatter(x=df.index, y=df[f"RSI{config.RSI_PERIOD}"], name="RSI14", line=dict(width=1)), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="gray", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="gray", row=3, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD", line=dict(width=1)), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], name="MACD Signal", line=dict(width=1)), row=4, col=1)
    macd_colors = ["#d62728" if v >= 0 else "#1f77b4" for v in df["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], name="MACD Histogram", marker_color=macd_colors), row=4, col=1)

    default_start = df.index[-DEFAULT_ZOOM_DAYS] if len(df) > DEFAULT_ZOOM_DAYS else df.index[0]

    default_range = [default_start, df.index[-1]]
    # matches(공유 x축)에 의존하지 않고, 4개 행 모두에 같은 초기 범위를 명시적으로 지정합니다.
    for r in (1, 2, 3, 4):
        fig.update_xaxes(range=default_range, row=r, col=1)

    fig.update_xaxes(
        row=1,
        col=1,
        rangeslider=dict(visible=False),  # 캔들스틱 기본 슬라이더는 끄고, 아래(row4)에 전용 슬라이더만 둡니다.
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1개월", step="month", stepmode="backward"),
                dict(count=3, label="3개월", step="month", stepmode="backward"),
                dict(count=6, label="6개월", step="month", stepmode="backward"),
                dict(count=1, label="1년", step="year", stepmode="backward"),
                dict(step="all", label="전체"),
            ],
            y=1.32,
            x=0,
            xanchor="left",
        ),
    )
    # 실제 확대/축소 슬라이더는 맨 아래(MACD) x축에 붙여서 전체 화면 높이를 아끼면서도 조절 가능하게 합니다.
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.08), row=4, col=1)

    fig.update_layout(
        height=1000,
        legend=dict(orientation="h", y=1.16, yanchor="bottom", x=0, xanchor="left"),
        margin=dict(t=160, b=10, l=10, r=10),
        hovermode="x unified",
        dragmode="pan",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"scrollZoom": True, "displaylogo": False},
    )


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


def _translate_signal_label(signal_text: str) -> str:
    return " & ".join(signals.SIGNAL_LABELS.get(part, part) for part in signal_text.split(" & "))


def render_signal_stats(df: pd.DataFrame) -> None:
    signal_cols = signals.get_signal_columns()

    with st.expander("📖 이 통계, 어떻게 읽어야 하나요? (꼭 한 번 읽어보세요)", expanded=False):
        st.markdown(
            f"""
- **발생횟수(count)**: 과거에 이 시그널(또는 조합)이 몇 번 발생했는지. **{config.MIN_SAMPLE_SIZE}번 미만이면
  "표본부족"으로 표시됩니다** — 몇 번 안 되는 사례로는 통계를 신뢰하기 어렵습니다.
- **baseline_mean_return**: 시그널과 상관없이 "그냥 아무 날"에 샀다면 평균적으로 어땠는지. 시그널의 평균 수익률과
  비교하는 기준선입니다.
- **excess_return**: (시그널 평균 수익률) − (baseline 평균 수익률). **양수여야 "이 시그널이 그냥 아무 날보다
  낫다"**는 뜻입니다.
- **pvalue**: 시그널 수익률이 baseline과 통계적으로 정말 다른지 검정한 값입니다. **0.05 미만이면 유의미**,
  0.05~0.1이면 약한 유의성, 0.1 이상이면 우연일 가능성이 높습니다.
- **confidence**: 표본수 + p-value를 종합한 한 줄 요약입니다. **"유의미"가 아니면 참고만 하고 맹신하지 마세요.**
- **net_mean_return / net_win_rate**: 거래비용(수수료+세금, 왕복 약 {config.ROUND_TRIP_COST_PCT:.2%} 가정)을
  뺀 뒤의 실질 수익률/승률입니다.
            """
        )

    st.markdown("#### 이 종목의 과거 시그널 통계")
    st.caption("이 종목의 지난 데이터에서 각 시그널(또는 최대 3개 조합)이 발생한 뒤 5/20/60거래일 후 수익률입니다.")

    stock_stats = backtest.compute_signal_stats(df, signal_cols)
    if stock_stats.empty:
        st.info("이 종목에서는 아직 발생한 시그널이 없습니다.")
    else:
        display_stats = stock_stats.copy()
        display_stats["signal"] = display_stats["signal"].map(_translate_signal_label)
        display_stats = display_stats.rename(columns={"signal": "시그널", "count": "발생횟수"})
        st.dataframe(style_stats_table(display_stats), use_container_width=True)

    st.markdown("---")
    st.markdown("#### 시장 추세(상승장/하락장)별 통계")
    st.caption("코스피/코스닥 지수가 자체 200일선 위(상승장)/아래(하락장)에 있을 때로 나눠서 봅니다.")
    regime_stats = backtest.compute_signal_stats_by_regime(df, signal_cols)
    if regime_stats.empty:
        st.info("시장 추세별로 나눌 만큼 시그널 발생 데이터가 충분하지 않습니다.")
    else:
        display_regime = regime_stats.copy()
        display_regime["signal"] = display_regime["signal"].map(_translate_signal_label)
        display_regime = display_regime.rename(
            columns={"signal": "시그널", "market_regime": "시장상황", "count": "발생횟수"}
        )
        st.dataframe(style_stats_table(display_regime), use_container_width=True)

    st.markdown("---")
    st.markdown("#### 전체 시장 기준 통계 (참고용)")
    market_stats_path = config.PROCESSED_DIR / "signal_stats.csv"
    if market_stats_path.exists():
        market_stats = pd.read_csv(market_stats_path)
        market_stats["signal"] = market_stats["signal"].map(_translate_signal_label)
        st.dataframe(
            style_stats_table(market_stats.rename(columns={"signal": "시그널", "count": "발생횟수"})),
            use_container_width=True,
        )
    else:
        st.info(
            "아직 전체 시장 통계 파일이 없습니다. 터미널(명령 프롬프트)에서 아래 명령어를 실행하면 "
            "여러 종목을 한꺼번에 분석해서 전체 시장 기준 통계를 만들 수 있어요:\n\n"
            "```\npython scripts/run_backtest.py --market ALL --limit 100\n```"
        )


def style_stats_table(stats: pd.DataFrame):
    pct_keywords = ["return", "rate", "prob", "drawdown"]
    pct_cols = [c for c in stats.columns if any(k in c for k in pct_keywords) and "pvalue" not in c]
    pvalue_cols = [c for c in stats.columns if "pvalue" in c]

    fmt = {c: "{:.2%}" for c in pct_cols}
    fmt.update({c: "{:.3f}" for c in pvalue_cols})

    styled = stats.style.format(fmt, na_rep="-")

    confidence_cols = [c for c in stats.columns if c.startswith("confidence_")]
    if confidence_cols:
        styled = styled.map(_highlight_confidence, subset=confidence_cols)
    return styled


def _highlight_confidence(value) -> str:
    if isinstance(value, str) and value.startswith("유의미"):
        return "color: #1a7f37; font-weight: 600;"
    if isinstance(value, str) and value in ("표본부족", "유의성없음"):
        return "color: #9a9a9a;"
    return ""


if __name__ == "__main__":
    main()
