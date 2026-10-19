// 이동평균 교차 전략 백테스트 (교육용 예시, 롱 온리, 전액 매수/전량 매도).
// 규칙: t일 종가로 교차가 확정되면 t+1일 시가에 체결. 신호 계산에는 t일까지의 데이터만 쓴다.
import { sma } from './indicators.js';

export const DEFAULTS = { short: 20, long: 60, feeRate: 0.001, slippageRate: 0.0005, warmup: 100, splitRatio: 0.7 };
export const GRID = { short: [5, 10, 20, 30], long: [40, 50, 60, 80, 100] };

// signals[t]: 'buy' | 'sell' | null — t일 종가 기준으로 확정된 신호
export function crossSignals(closes, short, long) {
  const s = sma(closes, short);
  const l = sma(closes, long);
  const out = new Array(closes.length).fill(null);
  for (let t = 1; t < closes.length; t++) {
    if (s[t - 1] == null || l[t - 1] == null) continue;
    if (s[t - 1] <= l[t - 1] && s[t] > l[t]) out[t] = 'buy';
    else if (s[t - 1] >= l[t - 1] && s[t] < l[t]) out[t] = 'sell';
  }
  return { signals: out, smaShort: s, smaLong: l };
}

function maxDrawdown(equity) {
  let peak = -Infinity;
  let mdd = 0;
  for (const e of equity) {
    peak = Math.max(peak, e);
    mdd = Math.min(mdd, e / peak - 1);
  }
  return mdd;
}

const buyFill = (price, c) => price * (1 + c.slippageRate);
const sellFill = (price, c) => price * (1 - c.slippageRate);

// [start, end] 구간(포함)을 현금 1.0에서 시작해 평가한다.
// 구간 마지막 날 보유 중이면 그날 종가에 비용을 반영해 청산한 것으로 계산한다.
export function runStrategy(bars, { short, long, feeRate, slippageRate, start, end }) {
  const c = { feeRate, slippageRate };
  const { signals } = crossSignals(bars.map((b) => b.close), short, long);
  let cash = 1;
  let shares = 0;
  let pending = null;
  let entry = null;
  let daysIn = 0;
  let unexecuted = 0;
  const equity = [];
  const trades = [];

  const sell = (t, raw, reason) => {
    const px = sellFill(raw, c);
    const gross = shares * px;
    const fee = gross * feeRate;
    cash = gross - fee;
    trades.push({ ...entry, exitSignalDate: reason === 'signal' ? bars[t - 1].time : null, exitDate: bars[t].time, exitPrice: px, exitFee: fee, exitReason: reason, returnPct: cash / entry.capital - 1 });
    shares = 0;
    entry = null;
  };

  for (let t = start; t <= end; t++) {
    const bar = bars[t];
    if (pending === 'buy' && shares === 0) {
      const px = buyFill(bar.open, c);
      const capital = cash;
      shares = capital / (px * (1 + feeRate));
      entry = { signalDate: bars[t - 1].time, entryDate: bar.time, entryPrice: px, entryFee: shares * px * feeRate, capital };
      cash = 0;
    } else if (pending === 'sell' && shares > 0) {
      sell(t, bar.open, 'signal');
    }
    pending = null;

    if (shares > 0) daysIn++;
    if (t === end && shares > 0) sell(t, bar.close, 'period_end');
    equity.push({ time: bar.time, value: cash + shares * bar.close });

    const sig = signals[t];
    if (sig && t < end) pending = sig;
    else if (sig && t === end) unexecuted++;
  }

  const values = equity.map((e) => e.value);
  return {
    totalReturn: values.at(-1) - 1,
    maxDrawdown: maxDrawdown(values),
    tradeCount: trades.length,
    winRate: trades.length ? trades.filter((x) => x.returnPct > 0).length / trades.length : null,
    exposure: daysIn / (end - start + 1),
    unexecutedSignals: unexecuted,
    equity,
    trades,
  };
}

// 같은 구간 단순 보유: 첫날 시가 매수, 마지막 날 종가 매도 (비용 동일 적용)
export function runBuyHold(bars, { feeRate, slippageRate, start, end }) {
  const c = { feeRate, slippageRate };
  const px = buyFill(bars[start].open, c);
  const shares = 1 / (px * (1 + feeRate));
  const equity = [];
  for (let t = start; t <= end; t++) {
    const v = t === end ? shares * sellFill(bars[t].close, c) * (1 - feeRate) : shares * bars[t].close;
    equity.push({ time: bars[t].time, value: v });
  }
  const values = equity.map((e) => e.value);
  return { totalReturn: values.at(-1) - 1, maxDrawdown: maxDrawdown(values), tradeCount: 1, equity };
}

// 평가 구간 나누기: 앞 warmup봉은 지표 준비용으로 제외, 나머지를 학습/검증으로 시간순 분할
export function splitPeriods(n, { warmup, splitRatio }) {
  const start = Math.min(warmup, n - 2);
  const evalLen = n - start;
  const isEnd = start + Math.max(1, Math.floor(evalLen * splitRatio)) - 1;
  return {
    inSample: { start, end: Math.min(isEnd, n - 2) },
    outSample: { start: Math.min(isEnd, n - 2) + 1, end: n - 1 },
    full: { start, end: n - 1 },
  };
}

// 학습 구간에서만 파라미터를 고른다 (누적수익률 기준). 검증 구간 데이터는 보지 않는다.
export function optimizeInSample(bars, costs, period) {
  const results = [];
  for (const short of GRID.short) {
    for (const long of GRID.long) {
      if (short >= long) continue;
      const r = runStrategy(bars, { short, long, ...costs, ...period });
      results.push({ short, long, totalReturn: r.totalReturn, maxDrawdown: r.maxDrawdown, tradeCount: r.tradeCount });
    }
  }
  results.sort((a, b) => b.totalReturn - a.totalReturn);
  return results;
}
