// 직접 작성한 캔버스 캔들 차트: 가격 패널(캔들·거래량·이동평균·매매 표시) + RSI 패널.
// 조작: 휠=확대/축소, 드래그=이동, 더블클릭=전체 보기.

const AXIS_W = 64;
const AXIS_H = 22;
const GAP = 10;

function niceStep(range, target) {
  const raw = range / Math.max(target, 1);
  const p = 10 ** Math.floor(Math.log10(raw));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export class CandleChart {
  constructor(canvas, legendEl) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.legend = legendEl;
    this.data = null;
    this.hover = null;
    this.view = { end: 0, count: 0 };
    this.#bindEvents();
    new ResizeObserver(() => this.draw()).observe(canvas);
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => this.draw());
  }

  setData(data, { keepView = false } = {}) {
    this.data = data;
    const n = data.bars.length;
    if (!keepView || this.view.count === 0 || this.view.end > n) this.view = { end: n, count: n };
    this.hover = null;
    this.draw();
  }

  #bindEvents() {
    const c = this.canvas;
    let drag = null;
    c.addEventListener('wheel', (e) => {
      if (!this.data) return;
      e.preventDefault();
      const n = this.data.bars.length;
      const { plotW } = this.#layout();
      const frac = Math.min(Math.max((e.offsetX) / plotW, 0), 1);
      const anchor = this.view.end - this.view.count * (1 - frac);
      const count = Math.round(Math.min(Math.max(this.view.count * (e.deltaY > 0 ? 1.15 : 1 / 1.15), 20), n));
      let end = anchor + count * (1 - frac);
      end = Math.min(Math.max(end, count), n);
      this.view = { end, count };
      this.draw();
    }, { passive: false });
    c.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, end: this.view.end }; c.setPointerCapture(e.pointerId); });
    c.addEventListener('pointerup', () => { drag = null; });
    c.addEventListener('pointermove', (e) => {
      if (!this.data) return;
      const { plotW } = this.#layout();
      if (drag) {
        const n = this.data.bars.length;
        const shift = ((e.clientX - drag.x) / plotW) * this.view.count;
        this.view.end = Math.min(Math.max(drag.end - shift, this.view.count), n);
      }
      this.hover = e.offsetX <= plotW ? { x: e.offsetX, y: e.offsetY } : null;
      this.draw();
    });
    c.addEventListener('pointerleave', () => { this.hover = null; this.draw(); });
    c.addEventListener('dblclick', () => { if (this.data) { this.setData(this.data); } });
  }

  #layout() {
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    const plotW = w - AXIS_W;
    const usable = h - AXIS_H - GAP;
    const mainH = Math.round(usable * (this.data?.show?.rsi === false ? 1 : 0.74));
    return { w, h, plotW, mainH, rsiTop: mainH + GAP, rsiH: usable - mainH };
  }

  draw() {
    const { canvas, ctx } = this;
    const dpr = window.devicePixelRatio || 1;
    const { w, h, plotW, mainH, rsiTop, rsiH } = this.#layout();
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!this.data || this.data.bars.length === 0) return;

    const col = {
      up: css('--up'), down: css('--down'), grid: css('--grid'), text: css('--muted'),
      ma1: css('--ma1'), ma2: css('--ma2'), rsi: css('--rsi'), cross: css('--fg'), vol: css('--vol'),
    };
    const { bars, maShort, maLong, rsi, markers = [], show } = this.data;
    const n = bars.length;
    const first = Math.max(0, Math.floor(this.view.end - this.view.count));
    const last = Math.min(n - 1, Math.ceil(this.view.end) - 1);
    const barW = plotW / this.view.count;
    const x = (i) => (i - (this.view.end - this.view.count) + 0.5) * barW;

    // 가격 범위
    let lo = Infinity, hi = -Infinity, vmax = 0;
    for (let i = first; i <= last; i++) {
      lo = Math.min(lo, bars[i].low);
      hi = Math.max(hi, bars[i].high);
      vmax = Math.max(vmax, bars[i].volume);
      for (const [on, s] of [[show.maShort, maShort], [show.maLong, maLong]]) if (on && s[i] != null) { lo = Math.min(lo, s[i]); hi = Math.max(hi, s[i]); }
    }
    const pad = (hi - lo) * 0.06 || 1;
    lo -= pad; hi += pad;
    const y = (v) => ((hi - v) / (hi - lo)) * mainH;

    ctx.font = '11px system-ui, sans-serif';
    ctx.lineWidth = 1;

    // 가격 격자·축
    const step = niceStep(hi - lo, mainH / 50);
    ctx.fillStyle = col.text;
    ctx.textBaseline = 'middle';
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
      const yy = Math.round(y(v)) + 0.5;
      ctx.strokeStyle = col.grid;
      ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(plotW, yy); ctx.stroke();
      ctx.fillText(v.toFixed(step < 1 ? 2 : 0), plotW + 6, yy);
    }

    // 날짜 축
    const every = Math.max(1, Math.ceil(80 / barW));
    ctx.textBaseline = 'top';
    ctx.textAlign = 'center';
    for (let i = first; i <= last; i++) {
      if (i % every) continue;
      const xx = Math.round(x(i)) + 0.5;
      ctx.strokeStyle = col.grid;
      ctx.beginPath(); ctx.moveTo(xx, 0); ctx.lineTo(xx, rsiTop + rsiH); ctx.stroke();
      const label = bars[i].time.slice(2, every > 15 ? 7 : 10);
      if (xx - ctx.measureText(label).width / 2 >= 0) ctx.fillText(label, xx, h - AXIS_H + 5);
    }
    ctx.textAlign = 'left';

    ctx.save();
    ctx.beginPath(); ctx.rect(0, 0, plotW, h); ctx.clip();

    // 거래량 (가격 패널 하단 18%)
    if (show.volume && vmax > 0) {
      ctx.fillStyle = col.vol;
      for (let i = first; i <= last; i++) {
        const vh = (bars[i].volume / vmax) * mainH * 0.18;
        ctx.fillRect(x(i) - barW * 0.35, mainH - vh, Math.max(1, barW * 0.7), vh);
      }
    }

    // 캔들
    const bodyW = Math.max(1, barW * 0.7);
    for (let i = first; i <= last; i++) {
      const b = bars[i];
      const up = b.close >= b.open;
      ctx.strokeStyle = ctx.fillStyle = up ? col.up : col.down;
      const xx = Math.round(x(i)) + 0.5;
      ctx.beginPath(); ctx.moveTo(xx, y(b.high)); ctx.lineTo(xx, y(b.low)); ctx.stroke();
      const top = y(Math.max(b.open, b.close));
      ctx.fillRect(x(i) - bodyW / 2, top, bodyW, Math.max(1, y(Math.min(b.open, b.close)) - top));
    }

    // 이동평균
    const line = (series, color, yf, from, to) => {
      ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.beginPath();
      let started = false;
      for (let i = from; i <= to; i++) {
        if (series[i] == null) { started = false; continue; }
        if (!started) { ctx.moveTo(x(i), yf(series[i])); started = true; } else ctx.lineTo(x(i), yf(series[i]));
      }
      ctx.stroke(); ctx.lineWidth = 1;
    };
    if (show.maShort) line(maShort, col.ma1, y, first, last);
    if (show.maLong) line(maLong, col.ma2, y, first, last);

    // 백테스트 체결 표시 (▲ 매수, ▼ 매도) — 체결된 봉 위치
    if (show.markers) {
      for (const m of markers) {
        if (m.index < first || m.index > last) continue;
        const b = bars[m.index];
        const xx = x(m.index);
        const buy = m.side === 'buy';
        const yy = buy ? y(b.low) + 6 : y(b.high) - 6;
        ctx.fillStyle = buy ? col.up : col.down;
        ctx.beginPath();
        ctx.moveTo(xx, buy ? yy : yy);
        ctx.lineTo(xx - 5, buy ? yy + 9 : yy - 9);
        ctx.lineTo(xx + 5, buy ? yy + 9 : yy - 9);
        ctx.closePath(); ctx.fill();
      }
    }
    ctx.restore();

    // RSI 패널
    if (show.rsi) {
      const ry = (v) => rsiTop + ((100 - v) / 100) * rsiH;
      ctx.strokeStyle = col.grid;
      ctx.strokeRect(0.5, rsiTop + 0.5, plotW - 1, rsiH - 1);
      ctx.setLineDash([4, 4]);
      ctx.textBaseline = 'middle';
      for (const lv of [30, 70]) {
        ctx.beginPath(); ctx.moveTo(0, Math.round(ry(lv)) + 0.5); ctx.lineTo(plotW, Math.round(ry(lv)) + 0.5); ctx.stroke();
        ctx.fillStyle = col.text; ctx.fillText(String(lv), plotW + 6, ry(lv));
      }
      ctx.setLineDash([]);
      ctx.fillText('RSI 14', 6, rsiTop + 10);
      ctx.save(); ctx.beginPath(); ctx.rect(0, rsiTop, plotW, rsiH); ctx.clip();
      line(rsi, col.rsi, ry, first, last);
      ctx.restore();
    }

    // 십자선 + 범례
    let idx = last;
    if (this.hover) {
      idx = Math.min(last, Math.max(first, Math.floor(this.hover.x / barW + (this.view.end - this.view.count))));
      ctx.strokeStyle = col.cross; ctx.globalAlpha = 0.4; ctx.setLineDash([3, 3]);
      const xx = Math.round(x(idx)) + 0.5;
      ctx.beginPath(); ctx.moveTo(xx, 0); ctx.lineTo(xx, rsiTop + rsiH); ctx.stroke();
      if (this.hover.y < mainH) {
        ctx.beginPath(); ctx.moveTo(0, this.hover.y + 0.5); ctx.lineTo(plotW, this.hover.y + 0.5); ctx.stroke();
        ctx.setLineDash([]); ctx.globalAlpha = 1;
        const price = hi - (this.hover.y / mainH) * (hi - lo);
        ctx.fillStyle = col.cross; ctx.fillRect(plotW, this.hover.y - 9, AXIS_W, 18);
        ctx.fillStyle = css('--bg'); ctx.fillText(price.toFixed(2), plotW + 6, this.hover.y);
      }
      ctx.setLineDash([]); ctx.globalAlpha = 1;
    }
    this.#renderLegend(idx);
  }

  #renderLegend(i) {
    if (!this.legend) return;
    const { bars, maShort, maLong, rsi, labels } = this.data;
    const b = bars[i];
    const f = (v) => (v == null ? '–' : v.toFixed(2));
    const chg = i > 0 ? (b.close / bars[i - 1].close - 1) * 100 : null;
    const period = b.lastTime ? `${b.time} ~ ${b.lastTime}` : b.time;
    this.legend.innerHTML = `
      <span class="lg-date">${period}</span>
      <span>시 <b>${f(b.open)}</b></span><span>고 <b>${f(b.high)}</b></span>
      <span>저 <b>${f(b.low)}</b></span><span>종 <b>${f(b.close)}</b></span>
      <span class="${chg >= 0 ? 'up' : 'down'}">${chg == null ? '' : `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`}</span>
      <span class="ma1">${labels.maShort} <b>${f(maShort[i])}</b></span>
      <span class="ma2">${labels.maLong} <b>${f(maLong[i])}</b></span>
      <span class="rsi">RSI14 <b>${f(rsi[i])}</b></span>`;
  }
}

// 간단한 수익곡선 차트 (전략 vs 단순 보유), 학습/검증 경계선 표시
export function drawEquity(canvas, series, splitTime) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!series.length || !series[0].points.length) return;
  const plotW = w - AXIS_W, plotH = h - AXIS_H;
  const n = series[0].points.length;
  let lo = Infinity, hi = -Infinity;
  for (const s of series) for (const p of s.points) { lo = Math.min(lo, p.value); hi = Math.max(hi, p.value); }
  const pad = (hi - lo) * 0.08 || 0.05; lo -= pad; hi += pad;
  const x = (i) => (i / (n - 1)) * plotW;
  const y = (v) => ((hi - v) / (hi - lo)) * plotH;
  ctx.font = '11px system-ui, sans-serif';
  ctx.textBaseline = 'middle';
  const step = niceStep(hi - lo, plotH / 40);
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    ctx.strokeStyle = css('--grid'); ctx.beginPath(); ctx.moveTo(0, Math.round(y(v)) + 0.5); ctx.lineTo(plotW, Math.round(y(v)) + 0.5); ctx.stroke();
    ctx.fillStyle = css('--muted'); ctx.fillText(`${((v - 1) * 100).toFixed(0)}%`, plotW + 6, y(v));
  }
  const pts = series[0].points;
  ctx.textBaseline = 'top';
  ctx.fillText(pts[0].time, 0, plotH + 5);
  ctx.textAlign = 'right'; ctx.fillText(pts.at(-1).time, plotW, plotH + 5); ctx.textAlign = 'left';
  const si = pts.findIndex((p) => p.time >= splitTime);
  if (si > 0) {
    ctx.strokeStyle = css('--muted'); ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x(si) + 0.5, 0); ctx.lineTo(x(si) + 0.5, plotH); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = css('--muted'); ctx.fillText('학습 | 검증', x(si) + 4, 4);
  }
  for (const s of series) {
    ctx.strokeStyle = s.color; ctx.lineWidth = 1.8; ctx.beginPath();
    s.points.forEach((p, i) => (i ? ctx.lineTo(x(i), y(p.value)) : ctx.moveTo(x(i), y(p.value))));
    ctx.stroke(); ctx.lineWidth = 1;
  }
}
