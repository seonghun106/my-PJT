"""종목 검색식(스크리너) 페이지 - HTS/MTS의 '조건검색식'처럼, 시장 전체에서
지금 특정 조건을 만족하는 종목을 찾아줍니다.

실행 방법: 메인 화면(streamlit run app.py)을 켜면 왼쪽 사이드바에 이 페이지가
자동으로 나타납니다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from src import config, data_loader, investor_flow, pipeline, screener

st.set_page_config(page_title="종목 검색식", page_icon="📡", layout="wide")


@st.cache_data(show_spinner="종목 목록을 불러오는 중...")
def load_stock_list() -> pd.DataFrame:
    return data_loader.get_stock_list()


@st.cache_data(show_spinner=False)
def load_screening_data(ticker: str, years: int) -> pd.DataFrame:
    return pipeline.build_screening_dataframe(ticker, years=years)


def format_won(x) -> str:
    if pd.isna(x):
        return "-"
    return f"{x / 1e8:,.1f}억원"


def main() -> None:
    st.title("📡 종목 검색식")
    st.caption("시장 전체를 스캔해서 지금 조건에 맞는 종목을 찾는 화면입니다 · 참고용이며 투자 조언이 아닙니다.")

    tab_screen, tab_flow = st.tabs(["🔎 종목 검색식 스캔", "💰 거래대금 순위 (기관/외국인)"])

    with tab_screen:
        render_screener_tab()

    with tab_flow:
        render_investor_flow_tab()


def render_screener_tab() -> None:
    with st.expander("📖 어떤 검색식들이 있나요?", expanded=False):
        for name in screener.get_screener_names():
            st.markdown(f"- **{screener.SCREENER_LABELS[name]}**: {screener.SCREENER_DESCRIPTIONS[name]}")

    stock_list = load_stock_list()

    col1, col2 = st.columns([1, 1])
    with col1:
        market_filter = st.selectbox("시장", ["전체", "KOSPI", "KOSDAQ"], key="screen_market")
    with col2:
        limit = st.slider(
            "스캔할 종목 수",
            min_value=20,
            max_value=config.SCREENER_MAX_LIMIT,
            value=config.SCREENER_DEFAULT_LIMIT,
            step=20,
            help="종목 수가 많을수록 정확하지만 느립니다. 캐시된 종목은 두 번째부터 훨씬 빨라집니다.",
        )

    selected_screens = st.multiselect(
        "실행할 검색식",
        options=screener.get_screener_names(),
        default=screener.get_screener_names(),
        format_func=lambda n: screener.SCREENER_LABELS[n],
    )

    st.caption(
        "⚠️ 종목 수가 많으면(특히 처음 실행 시) 시간이 꽤 걸릴 수 있습니다. "
        "먼저 적은 수로 테스트해보고 범위를 넓혀보세요."
    )

    run = st.button("🔍 검색 실행", type="primary", use_container_width=True)
    if not run:
        return

    if not selected_screens:
        st.warning("검색식을 하나 이상 선택해주세요.")
        return

    targets = stock_list if market_filter == "전체" else stock_list[stock_list["Market"] == market_filter]
    targets = targets.head(limit)

    results = {name: [] for name in selected_screens}
    progress = st.progress(0.0)
    status = st.empty()
    total = len(targets)

    for i, row in enumerate(targets.itertuples(), start=1):
        status.text(f"스캔 중... {row.Name} ({i}/{total})")
        progress.progress(i / total)
        try:
            df = load_screening_data(row.Code, config.YEARS_OF_DATA)
        except Exception:
            continue
        if df.empty:
            continue

        for name in selected_screens:
            match = screener.SCREENER_FUNCS[name](df)
            if match is not None:
                results[name].append({"Code": row.Code, "Name": row.Name, "Market": row.Market, **match})

    status.empty()
    progress.empty()
    st.success(f"스캔 완료: {total}개 종목 확인")

    for name in selected_screens:
        rows = results[name]
        st.markdown(f"#### {screener.SCREENER_LABELS[name]} — {len(rows)}개 종목")
        if not rows:
            st.info("조건을 만족하는 종목이 없습니다.")
            continue

        result_df = pd.DataFrame(rows)
        result_df = _sort_result(name, result_df)
        st.dataframe(style_result_table(result_df), use_container_width=True)


def _sort_result(name: str, df: pd.DataFrame) -> pd.DataFrame:
    sort_key = {
        "monthly_ma_breakout": "돌파월_거래량배수",
        "box_breakout": "돌파율",
        "volume_dryup_spike": "거래량배수",
    }.get(name)
    if sort_key and sort_key in df.columns:
        return df.sort_values(sort_key, ascending=False).reset_index(drop=True)
    return df.reset_index(drop=True)


def style_result_table(df: pd.DataFrame):
    pct_cols = [c for c in df.columns if "이격도" in c or "비율" in c or "박스폭" in c or "돌파율" in c]
    return df.style.format({c: "{:.2%}" for c in pct_cols}, na_rep="-")


def render_investor_flow_tab() -> None:
    st.caption(
        "한국거래소(KRX) 투자자별 매매 데이터를 사용합니다. 특정 기간 동안 기관/외국인이 "
        "가장 많이 순매수(사자 > 팔자)한 종목 순위입니다."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        market = st.selectbox("시장", ["KOSPI", "KOSDAQ"], key="flow_market")
    with col2:
        investor = st.selectbox("투자자", list(investor_flow.INVESTOR_OPTIONS.keys()), key="flow_investor")
    with col3:
        days = st.slider("최근 며칠간", min_value=5, max_value=60, value=config.INVESTOR_FLOW_DEFAULT_DAYS, key="flow_days")
    with col4:
        top_n = st.slider("표시 종목 수", min_value=10, max_value=100, value=config.INVESTOR_FLOW_TOP_N, key="flow_topn")

    if not st.button("💰 순매수 순위 조회", type="primary", use_container_width=True):
        return

    try:
        with st.spinner("KRX에서 데이터를 가져오는 중..."):
            ranking = investor_flow.get_net_purchase_ranking(
                market=market, investor=investor, lookback_days=days, top_n=top_n
            )
    except Exception as exc:
        st.error(
            f"데이터를 가져오지 못했습니다: {exc}\n\n"
            "네트워크 문제이거나, 조회 기간에 거래일이 없을 수 있습니다(주말/공휴일만 포함된 경우 등)."
        )
        return

    if ranking.empty:
        st.info("해당 조건에 맞는 데이터가 없습니다. 기간을 늘려서 다시 시도해보세요.")
        return

    display = ranking[["Code", "Name", "순매수거래대금", "순매수거래량", "매수거래대금", "매도거래대금"]].copy()
    for col in ["순매수거래대금", "매수거래대금", "매도거래대금"]:
        display[col] = ranking[col].map(format_won)
    display["순매수거래량"] = ranking["순매수거래량"].map(lambda x: f"{x:,.0f}주")

    st.dataframe(display, use_container_width=True)


if __name__ == "__main__":
    main()
