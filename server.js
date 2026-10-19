// 정적 파일 + 공개 시세 프록시 서버 (외부 의존성 없음).
// 시세 조회가 모두 실패하면 502 오류를 돌려줄 뿐, 대체(가짜) 데이터를 만들지 않는다.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const PUBLIC_DIR = join(fileURLToPath(new URL('.', import.meta.url)), 'public');
const HOST = '127.0.0.1';
const START_PORT = Number(process.env.PORT) || 4173;
const MAX_PORT_TRIES = 20;
const CACHE_MS = 10 * 60 * 1000;
const RANGES = { '1y': 1, '2y': 2, '5y': 5 };
const SYMBOL_RE = /^[A-Z0-9][A-Z0-9.\-]{0,14}$/;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
};

const cache = new Map();

function toDate(sec, offsetSec = 0) {
  return new Date((sec + offsetSec) * 1000).toISOString().slice(0, 10);
}

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { 'User-Agent': 'Mozilla/5.0 (personal chart app)', Accept: '*/*' },
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

async function fromYahoo(symbol, range) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=${range}&interval=1d&includePrePost=false`;
  const json = JSON.parse(await fetchText(url));
  const r = json?.chart?.result?.[0];
  if (!r) throw new Error(json?.chart?.error?.description || '응답에 결과가 없음');
  const q = r.indicators?.quote?.[0] ?? {};
  const offset = r.meta?.gmtoffset ?? 0;
  const bars = [];
  (r.timestamp ?? []).forEach((t, i) => {
    const o = q.open?.[i], h = q.high?.[i], l = q.low?.[i], c = q.close?.[i];
    if ([o, h, l, c].some((v) => v == null || !Number.isFinite(v))) return;
    bars.push({ time: toDate(t, offset), open: o, high: h, low: l, close: c, volume: q.volume?.[i] ?? 0 });
  });
  return {
    source: 'Yahoo Finance 차트 API (공개·비공식 엔드포인트)',
    sourceUrl: `https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}/history`,
    currency: r.meta?.currency ?? null,
    exchange: r.meta?.fullExchangeName ?? r.meta?.exchangeName ?? null,
    marketTime: r.meta?.regularMarketTime ? new Date(r.meta.regularMarketTime * 1000).toISOString() : null,
    note: '분할 반영 OHLC, 배당 미반영. 장중 값은 지연될 수 있음.',
    bars,
  };
}

async function fromStooq(symbol, range) {
  const years = RANGES[range];
  const end = new Date();
  const start = new Date(end);
  start.setUTCFullYear(end.getUTCFullYear() - years);
  const ymd = (d) => d.toISOString().slice(0, 10).replaceAll('-', '');
  const s = symbol.includes('.') ? symbol.toLowerCase() : `${symbol.toLowerCase()}.us`;
  const url = `https://stooq.com/q/d/l/?s=${encodeURIComponent(s)}&i=d&d1=${ymd(start)}&d2=${ymd(end)}`;
  const text = (await fetchText(url)).trim();
  const lines = text.split(/\r?\n/);
  if (!/^Date,Open,High,Low,Close/i.test(lines[0] ?? '')) throw new Error(`CSV 형식 아님: ${lines[0]?.slice(0, 60)}`);
  const bars = lines.slice(1).map((line) => {
    const [time, o, h, l, c, v] = line.split(',');
    return { time, open: +o, high: +h, low: +l, close: +c, volume: +v || 0 };
  }).filter((b) => [b.open, b.high, b.low, b.close].every(Number.isFinite));
  return {
    source: 'Stooq 일별 CSV (공개)',
    sourceUrl: `https://stooq.com/q/d/?s=${encodeURIComponent(s)}`,
    currency: null,
    exchange: null,
    marketTime: null,
    note: 'Stooq 조정 방식은 출처 기준.',
    bars,
  };
}

async function getHistory(symbol, range) {
  const key = `${symbol}:${range}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) return { ...hit.data, cached: true };

  const errors = [];
  for (const [name, fn] of [['Yahoo', fromYahoo], ['Stooq', fromStooq]]) {
    try {
      const data = await fn(symbol, range);
      if (data.bars.length < 2) throw new Error('유효한 봉이 부족함');
      data.bars.sort((a, b) => (a.time < b.time ? -1 : 1));
      const out = {
        symbol,
        range,
        ...data,
        fetchedAt: new Date().toISOString(),
        lastBarTime: data.bars.at(-1).time,
        attempts: [...errors, { source: name, ok: true }],
      };
      cache.set(key, { at: Date.now(), data: out });
      return out;
    } catch (err) {
      const cause = err?.cause ? ` (${err.cause.code || err.cause.message})` : '';
      errors.push({ source: name, ok: false, error: `${err?.message || err}${cause}` });
    }
  }
  const e = new Error('모든 공개 시세 소스 조회 실패');
  e.attempts = errors;
  throw e;
}

function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

async function handle(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (req.method !== 'GET') return send(res, 405, { error: 'GET만 지원' });

  if (url.pathname === '/api/history') {
    const symbol = (url.searchParams.get('symbol') || '').trim().toUpperCase();
    const range = url.searchParams.get('range') || '2y';
    if (!SYMBOL_RE.test(symbol)) return send(res, 400, { error: '종목 코드 형식이 올바르지 않음 (예: MU, AAPL, 005930.KS)' });
    if (!RANGES[range]) return send(res, 400, { error: '기간은 1y, 2y, 5y 중 하나' });
    try {
      return send(res, 200, await getHistory(symbol, range));
    } catch (err) {
      return send(res, 502, { error: err.message, attempts: err.attempts ?? [], checkedAt: new Date().toISOString() });
    }
  }

  const rel = url.pathname === '/' ? 'index.html' : normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, '');
  const file = join(PUBLIC_DIR, rel);
  if (!file.startsWith(PUBLIC_DIR)) return send(res, 403, { error: 'forbidden' });
  try {
    return send(res, 200, await readFile(file), MIME[extname(file)] ?? 'application/octet-stream');
  } catch {
    return send(res, 404, { error: 'not found' });
  }
}

function listen(port, triesLeft) {
  const server = http.createServer((req, res) => {
    handle(req, res).catch((err) => send(res, 500, { error: String(err) }));
  });
  server.once('error', (err) => {
    if (err.code === 'EADDRINUSE' && triesLeft > 0) {
      console.log(`포트 ${port} 사용 중 → ${port + 1} 시도`);
      listen(port + 1, triesLeft - 1);
    } else {
      console.error(err);
      process.exit(1);
    }
  });
  server.listen(port, HOST, () => {
    console.log(`주식 차트 앱 실행 중: http://localhost:${port}  (종료: Ctrl+C)`);
  });
}

listen(START_PORT, MAX_PORT_TRIES);
