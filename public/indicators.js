// 지표 계산. 모든 함수는 i번째 값을 0..i 데이터만으로 계산한다(미래 데이터 미사용).

export function sma(values, period) {
  const out = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

// Wilder 방식 RSI. 첫 값은 period개의 변화량 단순평균, 이후 지수 평활.
export function rsi(closes, period = 14) {
  const out = new Array(closes.length).fill(null);
  if (closes.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) gain += d; else loss -= d;
  }
  gain /= period;
  loss /= period;
  const value = () => (loss === 0 ? (gain === 0 ? 50 : 100) : 100 - 100 / (1 + gain / loss));
  out[period] = value();
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    gain = (gain * (period - 1) + Math.max(d, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = value();
  }
  return out;
}

// 일봉을 주봉(월요일 기준 주)·월봉으로 합친다. time은 'YYYY-MM-DD'.
export function aggregate(bars, interval) {
  if (interval === 'D') return bars;
  const keyOf = (time) => {
    if (interval === 'M') return time.slice(0, 7);
    const d = new Date(`${time}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return d.toISOString().slice(0, 10);
  };
  const out = [];
  let cur = null;
  let curKey = null;
  for (const b of bars) {
    const k = keyOf(b.time);
    if (k !== curKey) {
      cur = { ...b };
      curKey = k;
      out.push(cur);
    } else {
      cur.high = Math.max(cur.high, b.high);
      cur.low = Math.min(cur.low, b.low);
      cur.close = b.close;
      cur.volume += b.volume;
      cur.lastTime = b.time;
    }
  }
  return out;
}
