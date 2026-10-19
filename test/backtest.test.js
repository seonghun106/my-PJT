// 테스트 전용 합성 데이터만 사용한다 (앱은 합성/가짜 시세를 쓰지 않음).
import test from 'node:test';
import assert from 'node:assert/strict';
import { sma, rsi, aggregate } from '../public/indicators.js';
import { crossSignals, runStrategy, runBuyHold, splitPeriods, optimizeInSample, DEFAULTS } from '../public/backtest.js';

function synthBars(n, seed = 1) {
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const bars = [];
  let px = 100;
  const d = new Date('2024-01-01T00:00:00Z');
  for (let i = 0; i < n; i++) {
    const open = px * (1 + (rnd() - 0.5) * 0.01);
    const close = open * (1 + Math.sin(i / 25) * 0.01 + (rnd() - 0.5) * 0.03);
    bars.push({ time: d.toISOString().slice(0, 10), open, high: Math.max(open, close) * 1.01, low: Math.min(open, close) * 0.99, close, volume: 1000 + i });
    px = close;
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return bars;
}

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test('sma', () => {
  assert.deepEqual(sma([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
});

test('rsi: 계속 오르면 100, 계속 내리면 0, 첫 값은 period번째', () => {
  const up = Array.from({ length: 30 }, (_, i) => i + 1);
  const r = rsi(up, 14);
  assert.equal(r[13], null);
  assert.equal(r[14], 100);
  assert.equal(rsi(up.slice().reverse(), 14)[20], 0);
});

test('rsi: Wilder 평활 값 수기 계산과 일치', () => {
  const c = [10, 11, 10, 12, 11, 13];
  const r = rsi(c, 2);
  // 첫 2변화: +1, -1 → avgG=0.5, avgL=0.5 → 50
  close(r[2], 50);
  // d=+2: G=(0.5+2)/2=1.25, L=0.25 → 100-100/(1+5)
  close(r[3], 100 - 100 / 6);
});

test('aggregate 주봉/월봉', () => {
  const bars = synthBars(40);
  const w = aggregate(bars, 'W');
  const m = aggregate(bars, 'M');
  assert.equal(m.length, 2);
  assert.equal(m[0].close, bars[30].close); // 1월 마지막
  assert.equal(w[0].time, '2024-01-01'); // 2024-01-01은 월요일
  assert.equal(w[0].close, bars[6].close);
  assert.equal(w[0].high, Math.max(...bars.slice(0, 7).map((b) => b.high)));
});

test('신호 t일 → t+1일 시가 체결, 비용 반영', () => {
  const bars = synthBars(400);
  const { signals } = crossSignals(bars.map((b) => b.close), 20, 60);
  const costs = { feeRate: 0.001, slippageRate: 0.0005 };
  const r = runStrategy(bars, { short: 20, long: 60, ...costs, start: 100, end: 399 });
  assert.ok(r.tradeCount > 0);
  const idx = new Map(bars.map((b, i) => [b.time, i]));
  for (const t of r.trades) {
    const e = idx.get(t.entryDate);
    assert.equal(signals[e - 1], 'buy');
    assert.equal(bars[e - 1].time, t.signalDate);
    close(t.entryPrice, bars[e].open * 1.0005);
    if (t.exitReason === 'signal') {
      const x = idx.get(t.exitDate);
      assert.equal(signals[x - 1], 'sell');
      close(t.exitPrice, bars[x].open * 0.9995);
    }
  }
});

test('미래 데이터 미사용: t 이후 데이터를 바꿔도 t까지의 신호·체결·자산은 동일', () => {
  const bars = synthBars(400, 7);
  const cut = 250;
  const altered = bars.map((b, i) => (i > cut ? { ...b, open: b.open * 3, high: b.high * 3, low: b.low * 3, close: b.close * 3 } : b));
  const a = crossSignals(bars.map((b) => b.close), 20, 60).signals.slice(0, cut + 1);
  const b = crossSignals(altered.map((x) => x.close), 20, 60).signals.slice(0, cut + 1);
  assert.deepEqual(a, b);
  const p = { short: 20, long: 60, feeRate: 0.001, slippageRate: 0.0005, start: 100, end: 399 };
  const ra = runStrategy(bars, p).equity.slice(0, cut - 100 + 1);
  const rb = runStrategy(altered, p).equity.slice(0, cut - 100 + 1);
  assert.deepEqual(ra, rb);
});

test('비용 0이면 단순 보유 = 마지막 종가/첫 시가 - 1', () => {
  const bars = synthBars(200);
  const h = runBuyHold(bars, { feeRate: 0, slippageRate: 0, start: 10, end: 199 });
  close(h.totalReturn, bars[199].close / bars[10].open - 1);
  const h2 = runBuyHold(bars, { feeRate: 0.001, slippageRate: 0.0005, start: 10, end: 199 });
  close(h2.totalReturn + 1, (bars[199].close * 0.9995 * 0.999) / (bars[10].open * 1.0005 * 1.001));
  assert.ok(h.maxDrawdown <= 0);
});

test('구간 분할과 학습 구간 전용 최적화', () => {
  const n = 502;
  const p = splitPeriods(n, DEFAULTS);
  assert.equal(p.inSample.start, 100);
  assert.equal(p.outSample.start, p.inSample.end + 1);
  assert.equal(p.outSample.end, n - 1);
  const bars = synthBars(n, 3);
  const costs = { feeRate: 0.001, slippageRate: 0.0005 };
  const before = optimizeInSample(bars, costs, p.inSample);
  // 검증 구간 데이터를 바꿔도 최적화 결과는 그대로
  const altered = bars.map((b, i) => (i > p.inSample.end ? { ...b, open: 1, high: 1, low: 1, close: 1 } : b));
  assert.deepEqual(optimizeInSample(altered, costs, p.inSample), before);
});
