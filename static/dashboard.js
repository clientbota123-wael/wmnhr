const socket = io();
const grid = document.getElementById('grid');
const ts = document.getElementById('ts');
const latest = new Map();

const summaryBox = document.getElementById('summary');
const elTrend = document.getElementById('sum-trend');
const elConf = document.getElementById('sum-conf');
const elLiq = document.getElementById('sum-liq');
const elSpread = document.getElementById('sum-spread');
const elPress = document.getElementById('sum-press');
const elSumTs = document.getElementById('sum-ts');

function small(label, val, extra=''){
  return `<span class="px-2 py-0.5 rounded border bg-white/70 ${extra}">${label}: <b>${val}</b></span>`;
}

function tfBadge(tf, data){
  const dirCode = data.dir;
  const txt = dirCode === 1 ? 'صاعدة 🔼' : 'هابطة 🔽';
  const color = dirCode === 1 ? 'text-green-700' : 'text-red-700';
  const prob = ((data.conf||0)*100).toFixed(1)+'%';
  const t = (data.time||'').toString().split('T')[1]?.slice(0,8) || '—';

  const wave = data.wave ?? '—';
  const wtrend = data.wave_trend || 'غير محدد';
  const wcolor = wtrend === 'صاعد' ? 'text-green-700' : 'text-red-700';

  const rsi = data.rsi!=null ? Number(data.rsi).toFixed(1) : '—';
  const atr = data.atr!=null ? Number(data.atr).toFixed(6) : '—';
  const tp = data.tp_pct!=null ? Number(data.tp_pct).toFixed(2)+'%' : '—';

  const phase = data.trend_phase || 'Neutral';
  const phaseColor = data.trend_color || 'gray';
  const str = data.trend_strength != null ? Math.round(data.trend_strength*100) : null;
  let phaseCls = 'bg-gray-200 text-gray-800';
  if (phaseColor === 'green') phaseCls = 'bg-green-100 text-green-800';
  else if (phaseColor === 'yellow') phaseCls = 'bg-yellow-100 text-yellow-800';
  else if (phaseColor === 'red') phaseCls = 'bg-red-100 text-red-800';

  return `<div class="rounded-lg px-2 py-1 bg-white/80 border space-y-1">
    <div class="flex items-center justify-between">
      <div class="text-xs font-semibold">${tf}</div>
      <div class="text-xs ${color} font-bold">${txt}</div>
      <div class="text-[10px] text-gray-500">${prob}</div>
      <div class="text-[10px] text-gray-400">${t}</div>
    </div>
    <div class="flex items-center justify-between">
      <div class="text-[11px] ${wcolor}">الموجة: <b>${wave}</b> (${wtrend})</div>
      <div class="text-[10px] px-2 py-0.5 rounded-md border ${phaseCls}">Phase: <b>${phase}</b>${str!=null?` • ${str}%`:''}</div>
    </div>
    <div class="flex gap-2 flex-wrap text-[11px] mt-1">
      ${small('RSI', rsi)}
      ${small('ATR', atr)}
      ${small('TP', tp, 'text-indigo-700')}
    </div>
  </div>`;
}

function buildCard(sym, name){
  const card = document.createElement('div');
  card.className = 'card border rounded-xl p-3 bg-white shadow-sm transition-colors duration-300';
  card.setAttribute('data-symbol', sym);
  card.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="font-extrabold" data-name>${name || sym.replace('USDT','/USDT')}</div>
      <div class="text-xs text-gray-400" data-updated>—</div>
    </div>
    <div class="mt-1 text-sm">
      <span class="text-gray-500">السعر:</span>
      <span class="font-semibold" data-price>—</span>
      <span class="text-[10px] text-gray-400">USDT</span>
    </div>
    <div class="mt-2 space-y-1" data-tfs></div>
    <div class="mt-2 text-[11px]" data-extras>—</div>
    <div class="mt-2 text-[12px]" data-reco>—</div>
    <div class="mt-2 text-[12px]" data-timing>—</div>
  `;
  return card;
}

function setCardColor(card, dir){
  card.classList.remove('bg-green-50','bg-red-50');
  if (dir === 1) card.classList.add('bg-green-50');
  else card.classList.add('bg-red-50');
}

function fmtPct(x){
  if (x == null) return '—';
  return (x).toFixed(2) + '%';
}

function humanize(n){
  if (n == null) return '—';
  const absn = Math.abs(n);
  if (absn >= 1e9) return (n/1e9).toFixed(1)+'B';
  if (absn >= 1e6) return (n/1e6).toFixed(0)+'M';
  if (absn >= 1e3) return (n/1e3).toFixed(0)+'K';
  return Number(n).toFixed(0);
}

function renderRecommendation(rec){
  const act = rec?.action || 'انتظار';
  const tf = rec?.timeframe || '—';
  const conf = rec?.confidence_pct!=null ? rec.confidence_pct.toFixed(1)+'%' : '—';
  const mins = rec?.duration_min ?? '—';
  let cls = 'bg-gray-100 border text-gray-700';
  if (act === 'شراء') cls = 'bg-green-100 border text-green-800';
  if (act === 'بيع') cls = 'bg-red-100 border text-red-800';
  return `<div class="rounded-lg px-2 py-1 ${cls} flex items-center justify-between">
    <div>🔹 التوصية: <b>${act}</b> (${tf})</div>
    <div>الثقة: <b>${conf}</b></div>
    <div>صلاحية: <b>${mins} دقائق</b></div>
  </div>`;
}

function pressureLabel(p){
  if (p > 0.5) return '🔼 ضغط شرائي قوي';
  if (p > 0.0) return '🔼 ضغط شرائي';
  if (p < -0.5) return '🔽 ضغط بيعي قوي';
  if (p < 0.0) return '🔽 ضغط بيعي';
  return '⚪ ضغط محايد';
}

function rebuildGrid(){
  const entries = Array.from(latest.entries());
  entries.sort((a,b)=>{
    const aPrice = a[1]?.tfs?.['1m']?.price ?? 0;
    const bPrice = b[1]?.tfs?.['1m']?.price ?? 0;
    return bPrice - aPrice;
  });

  grid.innerHTML = '';
  for (const [sym, payload] of entries){
    const name = payload.name || sym.replace('USDT','/USDT');
    const card = buildCard(sym, name);
    grid.appendChild(card);

    const p = payload.tfs?.['1m']?.price ?? null;
    const priceEl = card.querySelector('[data-price]');
    if (p!=null) priceEl.textContent = Number(p).toFixed(6);

    const tfsEl = card.querySelector('[data-tfs]');
    const tfs = payload.tfs || {};
    ['1m','5m','10m'].forEach(tf => { if(!tfs[tf]) tfs[tf] = {dir:0,conf:0,time:null}; });
    tfsEl.innerHTML = ['1m','5m','10m'].map(tf => tfBadge(tf, tfs[tf])).join('');

    const dir1 = tfs['1m'].dir;
    setCardColor(card, dir1);

    const exEl = card.querySelector('[data-extras]');
    const sp = payload.extras?.spread_pct ?? null;
    const imb = payload.extras?.imbalance ?? null;
    const qv = payload.extras?.quote_volume_1m ?? null;
    const liq = payload.extras?.liq_bias_pct ?? null;
    const press = payload.extras?.pressure ?? 0.0;
    const imbColor = (imb ?? 0) >= 0 ? 'text-green-700' : 'text-red-700';
    const liqStr = liq==null ? '—' : (liq>=0?'+':'')+liq.toFixed(1)+'%';
    exEl.innerHTML = `
      <div class="flex items-center justify-between rounded-md px-2 py-1 bg-white/80 border">
        <span class="text-gray-600">سبريد: <b>${fmtPct(sp)}</b></span>
        <span class="text-gray-600">حجم: <b>${humanize(qv)}</b></span>
        <span class="${imbColor}">Imb: <b>${(imb==null?'—':(imb>=0?'+':'')+imb.toFixed(2))}</b></span>
      </div>
      <div class="flex items-center justify-between rounded-md px-2 py-1 bg-white/80 border mt-1">
        <span class="text-gray-600">سيولة: <b>${liqStr}</b></span>
        <span class="text-gray-700">${pressureLabel(press)}</span>
      </div>
    `;

    const recEl = card.querySelector('[data-reco]');
    recEl.innerHTML = renderRecommendation(payload.recommendation);

    const tmEl = card.querySelector('[data-timing]');
    const pm = payload.extras?.pred_minutes ?? null;
    if (pm!=null){
      tmEl.innerHTML = `<div class="text-[12px] px-2 py-1 rounded bg-amber-50 border border-amber-200">
        ⏱ تقدير زمني: <b>${Math.round(pm)} دقيقة</b> حتى تغيّر الاتجاه (تقريبي)
      </div>`;
    } else {
      tmEl.innerHTML = `<div class="text-[12px] text-gray-400">⏱ التقدير الزمني غير متاح بعد</div>`;
    }
  }
}

socket.on('top15_update', (payload)=>{
  ts.textContent = 'آخر تحديث: '+new Date().toLocaleTimeString();
  latest.set(payload.symbol, payload);
  rebuildGrid();
});

socket.on('market_summary', (s)=>{
  elSumTs.textContent = 'آخر تحديث: '+new Date().toLocaleTimeString();
  elConf.textContent = 'Avg Confidence: '+(s.avg_conf_pct!=null ? s.avg_conf_pct.toFixed(1)+'%' : '—');
  elLiq.textContent = 'Liquidity Bias: '+(s.liq_bias_pct!=null ? (s.liq_bias_pct>=0?'+':'')+s.liq_bias_pct.toFixed(1)+'%' : '—');
  elSpread.textContent = 'Avg Spread: '+(s.avg_spread_pct!=null ? s.avg_spread_pct.toFixed(2)+'%' : '—');
  elPress.textContent = 'Pressure: '+(s.pressure_label || '—');

  let trendBadge = 'Trend: —';
  let cls = 'bg-gray-100';
  if (s.trend === 'Bullish'){ trendBadge = 'Trend: 🟩 Bullish'; cls='bg-green-100'; }
  else if (s.trend === 'Bearish'){ trendBadge = 'Trend: 🟥 Bearish'; cls='bg-red-100'; }

  elTrend.textContent = trendBadge;
  elTrend.className = 'px-2 py-0.5 rounded '+cls;
  summaryBox.className = 'mt-2 rounded-lg border px-3 py-2 text-sm '+cls;
});
