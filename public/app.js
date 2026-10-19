import { sma, rsi, aggregate } from './indicators.js';
import { DEFAULTS, runStrategy, runBuyHold, splitPeriods, optimizeInSample } from './backtest.js';
import { CandleChart, drawEquity } from './chart.js';

const $ = (id) => document.getElementById(id);
const WATCH_KEY = 'my-chart.watchlist.v1';
const MA_SHORT = 20;
const MA_LONG = 60;

const state = {
  symbol: (new URLSearchParams(location.search).get('symbol') || 'MU').toUpperCase(),
  range: '2y',
  interval: 'D',
  payload: null, // 서버 응답 (실제 시세만)
  view: null, // 현재 주기 봉 + 지표
  bt: null,
};

const chart = new CandleChart($('chart'), $('legend'));

// ---------- 관심종목 (localStorage, 실패해도 동작) ----------
function loadWatch() {
  try {
    const v = JSON.parse(localStorage.getItem(WATCH_KEY));
    if (Array.isArray(v)) return v.filter((s) => typeof s === 'string');
  } catch { /* 저장소 사용 불가 */ }
  return ['MU'];
}
let watch = loadWatch();
function saveWatch() {
  try { localStorage.setItem(WATCH_KEY, JSON.stringify(watch)); } catch { /* 무시 */ }
}
function renderWatch() {
  const ul = $('watchlist');
  ul.replaceChildren(...watch.map((s) => {
    const li = document.createElement('li');
    li.className = s === state.symbol ? 'active' : '';
    const b = document.createElement('button');
    b.className = 'sym'; b.type = 'button'; b.textContent = s;
    b.onclick = () => { $('symbol-input').value = s; load(s); };
    const rm = document.createElement('button');
    rm.className = 'rm'; rm.type = 'button'; rm.textContent = '×'; rm.title = `${s} 삭제`;
    rm.onclick = () => { watch = watch.filter((x) => x !== s); saveWatch(); renderWatch(); };
    li.append(b, rm);
    return li;
  }));
  if (!watch.length) ul.innerHTML = '<li class="muted">비어 있음</li>';
  $('watch-add').textContent = watch.includes(state.symbol) ? '★ 관심' : '☆ 관심';
}

// ---------- 데이터 조회 ----------
function showMsg(text, isError = false) {
  const el = $('chart-msg');
  el.hidden = !text;
  el.textContent = text || '';
  el.classList.toggle('error', isError);
}

async function load(symbol) {
  state.symbol = symbol.toUpperCase();
  history.replaceState(null, '', `?symbol=${encodeURIComponent(state.symbol)}`);
  $('title-symbol').textContent = state.symbol;
  $('title-meta').textContent = '';
  renderWatch();
  showMsg('실제 시세를 불러오는 중…');
  try {
    const res = await fetch(`/api/history?symbol=${encodeURIComponent(state.symbol)}&range=${state.range}`);
    const body = await res.json();
    if (!res.ok) {
      const detail = (body.attempts || []).map((a) => `· ${a.source}: ${a.error}`).join('\n');
      throw new Error(`${body.error}${detail ? `\n${detail}` : ''}`);
    }
    state.payload = body;
    showMsg('');
    rebuildView();
    runBacktest();
  } catch (err) {
    // 실패 시 이전 종목 데이터나 가짜 시세를 보여주지 않는다.
    state.payload = null;
    state.view = null;
    state.bt = null;
    chart.setData({ bars: [], maShort: [], maLong: [], rsi: [], show: {}, labels: {} });
    $('legend').textContent = '';
    $('source-line').textContent = `시세 조회 실패 (${new Date().toLocaleString()}) — 가짜 데이터로 대체하지 않습니다.`;
    clearBacktest('시세가 없어 백테스트를 실행하지 않았습니다.');
    showMsg(`${state.symbol} 시세를 가져오지 못했습니다.\n${err.message}`, true);
  }
}

function fmtTime(iso) {
  return iso ? new Date(iso).toLocaleString() : '–';
}

function rebuildView({ keepView = false } = {}) {
  const p = state.payload;
  if (!p) return;
  const bars = aggregate(p.bars, state.interval);
  const closes = bars.map((b) => b.close);
  const unit = { D: '일', W: '주', M: '개월' }[state.interval];
  state.view = {
    bars,
    maShort: sma(closes, MA_SHORT),
    maLong: sma(closes, MA_LONG),
    rsi: rsi(closes, 14),
    labels: { maShort: `MA${MA_SHORT}`, maLong: `MA${MA_LONG}` },
    unit,
  };
  updateChart(keepView);
  const last = p.bars.at(-1);
  $('title-meta').textContent = `${p.exchange ?? ''} ${p.currency ?? ''} · 종가 ${last.close.toFixed(2)} (${last.time})`;
  const src = $('source-line');
  src.innerHTML = '';
  src.append('데이터 출처: ');
  const a = document.createElement('a');
  a.href = p.sourceUrl; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = p.source;
  src.append(a, ` · 마지막 봉 ${p.lastBarTime}`, p.marketTime ? ` · 출처 기준 시각 ${fmtTime(p.marketTime)}` : '',
    ` · 조회 시각 ${fmtTime(p.fetchedAt)}${p.cached ? ' (10분 캐시)' : ''} · ${p.bars.length}개 일봉 · ${p.note}`,
    state.interval !== 'D' ? ` · ${unit}봉은 일봉을 합친 값, 이동평균·RSI는 ${unit}봉 기준` : '');
}

function updateChart(keepView = true) {
  if (!state.view) return;
  const show = Object.fromEntries(['maShort', 'maLong', 'rsi', 'volume', 'markers'].map((k) => [k, $(`show-${k}`).checked]));
  let markers = [];
  if (state.interval === 'D' && state.bt) {
    const idx = new Map(state.view.bars.map((b, i) => [b.time, i]));
    for (const t of state.bt.full.trades) {
      markers.push({ index: idx.get(t.entryDate), side: 'buy' });
      if (t.exitReason === 'signal') markers.push({ index: idx.get(t.exitDate), side: 'sell' });
    }
    markers = markers.filter((m) => m.index != null);
  }
  chart.setData({ ...state.view, show, markers }, { keepView });
}

// ---------- 백테스트 ----------
const pct = (v, digits = 2) => (v == null ? '–' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`);

function readParams() {
  const short = Math.round(Number($('bt-short').value));
  const long = Math.round(Number($('bt-long').value));
  const fee = Number($('bt-fee').value);
  const slip = Number($('bt-slip').value);
  if (!(short >= 2 && long <= DEFAULTS.warmup && short < long)) throw new Error(`단기(≥2) < 장기(≤${DEFAULTS.warmup}) 이어야 합니다.`);
  if (!(fee >= 0 && fee <= 5 && slip >= 0 && slip <= 5)) throw new Error('수수료·슬리피지는 0~5% 범위로 입력하세요.');
  return { short, long, feeRate: fee / 100, slippageRate: slip / 100, splitRatio: Number($('bt-split').value) };
}

function clearBacktest(msg) {
  $('bt-periods').textContent = msg;
  $('bt-table').innerHTML = '';
  $('bt-opt').textContent = '';
  $('trade-table').innerHTML = '';
  drawEquity($('equity'), [], '');
}

function runBacktest() {
  const p = state.payload;
  if (!p) return clearBacktest('시세가 없어 백테스트를 실행하지 않았습니다.');
  let params;
  try { params = readParams(); } catch (err) { return clearBacktest(err.message); }
  const bars = p.bars; // 백테스트는 항상 일봉
  if (bars.length < DEFAULTS.warmup + 40) return clearBacktest(`일봉이 부족합니다 (${bars.length}개, 최소 ${DEFAULTS.warmup + 40}개).`);

  const periods = splitPeriods(bars.length, { warmup: DEFAULTS.warmup, splitRatio: params.splitRatio });
  const costs = { feeRate: params.feeRate, slippageRate: params.slippageRate };
  const run = (period, s = params.short, l = params.long) => ({
    strat: runStrategy(bars, { short: s, long: l, ...costs, ...period }),
    hold: runBuyHold(bars, { ...costs, ...period }),
  });
  const is = run(periods.inSample);
  const oos = run(periods.outSample);
  const full = run(periods.full);
  const grid = optimizeInSample(bars, costs, periods.inSample);
  const best = grid[0];
  const bestOos = runStrategy(bars, { short: best.short, long: best.long, ...costs, ...periods.outSample });
  state.bt = { full: full.strat };

  const range = (pr) => `${bars[pr.start].time} ~ ${bars[pr.end].time} (${pr.end - pr.start + 1}일)`;
  $('bt-periods').innerHTML = `지표 준비: ${bars[0].time} ~ ${bars[periods.full.start - 1].time} ·
    <b>학습(조정)</b> ${range(periods.inSample)} · <b>검증</b> ${range(periods.outSample)} ·
    비용: 수수료 ${(params.feeRate * 100).toFixed(2)}% + 슬리피지 ${(params.slippageRate * 100).toFixed(2)}% (매수·매도 각각)`;

  const row = (label, name, r, isHold) => `<tr><td>${label}</td><td>${name}</td>
    <td class="${r.totalReturn >= 0 ? 'up' : 'down'}">${pct(r.totalReturn)}</td>
    <td class="down">${pct(r.maxDrawdown)}</td>
    <td>${isHold ? '1 (보유)' : r.tradeCount}</td>
    <td>${isHold ? '–' : pct(r.winRate, 0).replace('+', '')}</td>
    <td>${isHold ? '100%' : pct(r.exposure, 0).replace('+', '')}</td></tr>`;
  const name = `MA${params.short}/${params.long} 교차`;
  $('bt-table').innerHTML = `<thead><tr><th>구간</th><th>방식</th><th>누적수익률</th><th>최대낙폭</th><th>거래 수</th><th>승률</th><th>보유 비중</th></tr></thead>
    <tbody>
      ${row('학습', name, is.strat)}${row('학습', '단순 보유', is.hold, true)}
      ${row('검증', name, oos.strat)}${row('검증', '단순 보유', oos.hold, true)}
      ${row('전체', name, full.strat)}${row('전체', '단순 보유', full.hold, true)}
    </tbody>`;

  $('bt-opt').innerHTML = `<b>학습 구간 파라미터 탐색</b> (단기 ${[5, 10, 20, 30].join('/')} × 장기 ${[40, 50, 60, 80, 100].join('/')}, 학습 구간 누적수익률 기준, 검증 데이터 미사용):
    최적 MA${best.short}/${best.long} → 학습 ${pct(best.totalReturn)} · <b>검증 ${pct(bestOos.totalReturn)}</b> (최대낙폭 ${pct(bestOos.maxDrawdown)}, 거래 ${bestOos.tradeCount}회)
    / 같은 검증 구간 단순 보유 ${pct(oos.hold.totalReturn)}.
    <span class="muted">학습 구간에서 고른 값은 과적합될 수 있어, 검증 구간 결과로 판단해야 합니다.</span>
    <button type="button" id="bt-apply-best">MA${best.short}/${best.long} 적용</button>`;
  $('bt-apply-best').onclick = () => { $('bt-short').value = best.short; $('bt-long').value = best.long; runBacktest(); };

  const splitTime = bars[periods.outSample.start].time;
  state.equityArgs = [[
    { color: getComputedStyle(document.documentElement).getPropertyValue('--hold'), points: full.hold.equity },
    { color: getComputedStyle(document.documentElement).getPropertyValue('--ma1'), points: full.strat.equity },
  ], splitTime];
  drawEquity($('equity'), ...state.equityArgs);

  const tr = full.strat.trades;
  $('trade-table').innerHTML = `<thead><tr><th>#</th><th>매수 신호(종가)</th><th>매수 체결(시가)</th><th>매수가</th><th>매도 신호(종가)</th><th>매도 체결</th><th>매도가</th><th>수익률</th></tr></thead>
    <tbody>${tr.map((t, i) => `<tr><td>${i + 1}</td><td>${t.signalDate}</td><td>${t.entryDate}</td><td>${t.entryPrice.toFixed(2)}</td>
      <td>${t.exitSignalDate ?? '–'}</td><td>${t.exitDate}${t.exitReason === 'period_end' ? ' (기간 종료 종가 청산)' : ''}</td><td>${t.exitPrice.toFixed(2)}</td>
      <td class="${t.returnPct >= 0 ? 'up' : 'down'}">${pct(t.returnPct)}</td></tr>`).join('') || '<tr><td colspan="8">거래 없음</td></tr>'}</tbody>`;
  updateChart(true);
}

// ---------- CSV ----------
function downloadCsv(filename, metaLines, header, rows) {
  const esc = (v) => (v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v));
  const text = [...metaLines.map((m) => `# ${m}`), header.join(','), ...rows.map((r) => r.map(esc).join(','))].join('\r\n');
  const blob = new Blob(['﻿', text], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const r4 = (v) => (v == null ? '' : Math.round(v * 1e4) / 1e4);
function sourceMeta() {
  const p = state.payload;
  return [`symbol: ${p.symbol}`, `source: ${p.source} (${p.sourceUrl})`, `last_bar: ${p.lastBarTime}`, `fetched_at: ${p.fetchedAt}`];
}

$('csv-bars').onclick = () => {
  if (!state.view) return alert('내보낼 시세가 없습니다.');
  const v = state.view;
  downloadCsv(`${state.symbol}_${state.interval}_${state.payload.lastBarTime}.csv`, [...sourceMeta(), `interval: ${state.interval}`],
    ['date', 'open', 'high', 'low', 'close', 'volume', `ma${MA_SHORT}`, `ma${MA_LONG}`, 'rsi14'],
    v.bars.map((b, i) => [b.time, r4(b.open), r4(b.high), r4(b.low), r4(b.close), b.volume, r4(v.maShort[i]), r4(v.maLong[i]), r4(v.rsi[i])]));
};
$('csv-trades').onclick = () => {
  if (!state.bt) return alert('내보낼 거래가 없습니다.');
  const p = readParams();
  downloadCsv(`${state.symbol}_trades_MA${p.short}-${p.long}.csv`,
    [...sourceMeta(), `strategy: MA${p.short}/${p.long} cross, fill next open`, `fee_each_side: ${p.feeRate}`, `slippage_each_side: ${p.slippageRate}`],
    ['signal_date', 'entry_date', 'entry_price', 'entry_fee', 'exit_signal_date', 'exit_date', 'exit_price', 'exit_fee', 'exit_reason', 'return'],
    state.bt.full.trades.map((t) => [t.signalDate, t.entryDate, r4(t.entryPrice), t.entryFee, t.exitSignalDate, t.exitDate, r4(t.exitPrice), t.exitFee, t.exitReason, r4(t.returnPct)]));
};

// ---------- 이벤트 ----------
$('symbol-form').addEventListener('submit', (e) => {
  e.preventDefault();
  state.range = $('range-select').value;
  const s = $('symbol-input').value.trim().toUpperCase();
  if (s) load(s);
});
$('watch-add').onclick = () => {
  if (watch.includes(state.symbol)) watch = watch.filter((x) => x !== state.symbol);
  else watch.push(state.symbol);
  saveWatch(); renderWatch();
};
document.querySelectorAll('[data-interval]').forEach((btn) => {
  btn.onclick = () => {
    state.interval = btn.dataset.interval;
    document.querySelectorAll('[data-interval]').forEach((b) => b.classList.toggle('on', b === btn));
    rebuildView();
  };
});
['maShort', 'maLong', 'rsi', 'volume', 'markers'].forEach((k) => $(`show-${k}`).addEventListener('change', () => updateChart(true)));
$('bt-form').addEventListener('submit', (e) => { e.preventDefault(); runBacktest(); });
$('bt-reset').onclick = () => {
  $('bt-short').value = DEFAULTS.short; $('bt-long').value = DEFAULTS.long;
  $('bt-fee').value = DEFAULTS.feeRate * 100; $('bt-slip').value = DEFAULTS.slippageRate * 100;
  $('bt-split').value = String(DEFAULTS.splitRatio);
  runBacktest();
};
addEventListener('resize', () => { if (state.bt && state.equityArgs) drawEquity($('equity'), ...state.equityArgs); });

$('symbol-input').value = state.symbol;
load(state.symbol);
