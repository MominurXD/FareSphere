import { greatCircleArc, latLonToXYZ, projectPoint, rotatePoint } from './geometry.mjs';

const API = '/api/v1';
const state = {
  providers: [], network: [], journey: null, results: null,
  yaw: -0.05, pitch: -0.32, scale: 1.0, dragging: false, lastX: 0, lastY: 0,
};

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  let body = {};
  try { body = await response.json(); } catch { /* no-op */ }
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function setDefaultDate() {
  const d = new Date(); d.setDate(d.getDate() + 21);
  $('departure-date').value = d.toISOString().slice(0, 10);
}

function configuredFlightProvider() {
  return state.providers.find((p) => p.kind === 'flights' && p.configured);
}

const LONDON_GROUND_CODES = new Set(['LON','LHR','LCY','LGW','LTN','STN']);

function isLondonGroundRoute() {
  const origin = $('origin').value.trim().toUpperCase();
  const destination = $('destination').value.trim().toUpperCase();
  return origin !== destination && LONDON_GROUND_CODES.has(origin) && LONDON_GROUND_CODES.has(destination);
}

function updateSearchMode() {
  const pill = $('flight-state');
  const button = $('live-search');
  if (isLondonGroundRoute()) {
    pill.className = 'state-pill live';
    pill.textContent = 'LIVE · TFL JOURNEY + FARE';
    if (!button.disabled) button.innerHTML = 'Search live journey <b>→</b>';
    return;
  }

  const flights = configuredFlightProvider();
  pill.className = `state-pill ${flights ? 'live' : 'offline'}`;
  pill.textContent = flights ? `LIVE · ${flights.name.toUpperCase()}` : 'LIVE PROVIDER UNAVAILABLE';
  if (!button.disabled) button.innerHTML = 'Search live fares <b>→</b>';
}

async function loadProviders() {
  try {
    const [providers, health] = await Promise.all([api('/providers'), api('/health')]);
    state.providers = providers;
    const configured = providers.filter((p) => p.configured).length;
    $('provider-count').textContent = `${configured}/${providers.length}`;
    $('provider-items').innerHTML = providers.map((p) => `
      <div class="provider"><span class="provider-dot ${p.configured ? 'live' : ''}"></span><div><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(p.configured ? p.purpose : p.setup_hint)}</small></div></div>`).join('');

    $('live-search').disabled = false;
    updateSearchMode();
    $('sample-search').classList.toggle('hidden', !health.sample_data_enabled);

    const tfl = providers.find((p) => p.id === 'tfl');
    if (tfl?.configured) await loadNetwork();
    else $('network-status-text').textContent = 'TfL unavailable — no line data is fabricated';
  } catch (error) {
    $('network-status-text').textContent = `Provider check failed: ${error.message}`;
  }
}

async function loadNetwork() {
  try {
    $('network-status-text').textContent = 'Loading live TfL line geometry…';
    const data = await api('/network/london');
    state.network = data.paths || [];
    $('network-status-text').textContent = `${state.network.length} live TfL line paths loaded`;
  } catch (error) {
    state.network = [];
    $('network-status-text').textContent = error.message;
  }
}

function currency(value, code = 'GBP') {
  return new Intl.NumberFormat('en-GB', { style: 'currency', currency: code }).format(value);
}
function duration(minutes) { return `${Math.floor(minutes / 60)}h ${minutes % 60}m`; }
function fmtTime(value) { return new Date(value).toLocaleString('en-GB', { day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }); }

function searchPayload(sample = false) {
  return {
    origin: $('origin').value.trim().toUpperCase(), destination: $('destination').value.trim().toUpperCase(),
    departure_date: $('departure-date').value, departure_time: $('departure-time').value || '09:00',
    passengers: Number($('passengers').value), checked_bags: 0,
    flexible_days: sample ? 2 : 0, sort: $('sort').value,
  };
}

async function runSearch(sample = false) {
  const errorBox = $('search-error'); errorBox.classList.add('hidden');
  $('live-search').textContent = sample ? 'Loading sample…' : 'Searching live providers…';
  try {
    const data = await api(sample ? '/sample/search' : '/search', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(searchPayload(sample)),
    });
    renderResults(data);
  } catch (error) {
    errorBox.textContent = error.message; errorBox.classList.remove('hidden');
  } finally {
    updateSearchMode();
  }
}

function renderResults(data) {
  state.results = data;
  state.journey = data.results?.[0] || null;
  $('results').classList.remove('hidden');
  $('route-title').textContent = `${data.origin.name} → ${data.destination.name}`;
  $('results-mode').textContent = data.data_mode === 'live' ? 'Verified live results' : 'Sample preview';
  $('results-notice').textContent = data.notice || '';
  $('data-badge').className = `data-badge ${data.data_mode === 'live' ? 'live' : 'sample'}`;
  $('data-badge').textContent = `${data.data_mode.toUpperCase()} · ${data.providers_used.join(', ')}`;
  $('result-count').textContent = `${data.results.length} provider result${data.results.length === 1 ? '' : 's'}`;
  $('result-time').textContent = `Fetched ${new Date(data.generated_at).toLocaleTimeString('en-GB')}`;

  if (data.flexible_date_savings?.length) {
    $('date-strip').classList.remove('hidden');
    $('date-strip').innerHTML = data.flexible_date_savings.map((item) => {
      const d = new Date(`${item.date}T12:00:00`);
      return `<div class="date-card"><div><span>${d.toLocaleDateString('en-GB',{weekday:'short'})}</span><small>${d.toLocaleDateString('en-GB',{day:'numeric',month:'short'})}</small></div><strong>${currency(item.from_price,data.currency)}</strong>${item.saving > 0 ? `<em>save ${currency(item.saving,data.currency)}</em>` : ''}</div>`;
    }).join('');
  } else {
    $('date-strip').classList.add('hidden'); $('date-strip').innerHTML = '';
  }

  $('journey-list').innerHTML = data.results.map((journey, index) => journeyCard(journey, index === 0)).join('');
  document.querySelectorAll('.journey-card').forEach((button) => button.addEventListener('click', () => selectJourney(button.dataset.id)));
  renderDetail(state.journey);
  $('results').scrollIntoView({ behavior:'smooth', block:'start' });
}

function journeyCard(j, active) {
  const legs = j.legs.map((leg) => `<span class="leg-chip">${leg.mode === 'flight' ? '✈' : leg.mode === 'train' ? '▰' : '●'} ${escapeHtml(leg.origin.code)} → ${escapeHtml(leg.destination.code)}</span>`).join('');
  const emissions = j.total_emissions_kg == null ? '' : `<span>◌ ${escapeHtml(j.total_emissions_kg)}kg CO₂e</span>`;
  return `<button class="journey-card ${active ? 'active' : ''}" data-id="${escapeHtml(j.id)}"><div class="journey-top"><div><div class="badges">${j.badges.map((b)=>`<span class="badge">${escapeHtml(b)}</span>`).join('')}<span class="badge ${j.price_verified ? 'verified' : 'sample'}">${j.price_verified ? 'verified price' : 'sample price'}</span></div><h3>${escapeHtml(j.label)}</h3></div><div class="price"><strong>${currency(j.total_price,j.currency)}</strong>${j.savings_vs_baseline > 0 ? `<small>save ${currency(j.savings_vs_baseline,j.currency)}</small>` : ''}</div></div><div class="leg-list">${legs}</div><div class="journey-meta"><span>◷ ${duration(j.total_duration_minutes)}</span>${emissions}<span>◇ risk ${j.risk_score}/100</span><span>${escapeHtml(j.source)}</span></div></button>`;
}

function selectJourney(id) {
  if (!state.results) return;
  state.journey = state.results.results.find((j) => j.id === id) || state.results.results[0];
  document.querySelectorAll('.journey-card').forEach((el) => el.classList.toggle('active', el.dataset.id === state.journey.id));
  renderDetail(state.journey);
}

function renderDetail(j) {
  if (!j) { $('journey-detail').innerHTML = ''; return; }
  const riskClass = j.risk_score > 35 ? 'medium' : 'low';
  const booking = j.booking_url ? `<p><a href="${escapeHtml(j.booking_url)}" target="_blank" rel="noopener noreferrer">Check this live price with provider ↗</a></p>` : '';
  $('journey-detail').innerHTML = `<div class="detail-head"><span class="eyebrow">Selected route</span><span class="risk ${riskClass}">risk ${j.risk_score}/100</span></div><h3>${escapeHtml(j.label)}</h3><div class="detail-price"><strong>${currency(j.total_price,j.currency)}</strong><span>${j.price_verified ? 'Provider-verified search price' : 'Sample price'}</span></div><div>${j.legs.map((leg,index)=>`<div class="timeline-step"><span class="step-number">${index+1}</span><div><strong>${escapeHtml(leg.origin.name)} → ${escapeHtml(leg.destination.name)}</strong><p>${escapeHtml(leg.carrier)}${leg.number ? ` · ${escapeHtml(leg.number)}` : ''} · ${escapeHtml(leg.mode)}</p><small>${fmtTime(leg.depart_at)} → ${new Date(leg.arrive_at).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})}</small></div></div>`).join('')}</div>${booking}<div class="provenance"><strong>Data provenance</strong><br>${escapeHtml(j.source)}. Live prices may change; revalidate an offer before booking.</div>`;
}

async function loadDepartures() {
  const errorBox = $('rail-error'); errorBox.classList.add('hidden');
  const crs = $('station').value.trim().toUpperCase();
  try {
    const data = await api(`/rail/departures/${encodeURIComponent(crs)}`);
    $('departures-panel').innerHTML = `<div class="departure-head"><strong>${escapeHtml(data.station)}</strong><span>LIVE · ${escapeHtml(data.provider)}</span></div>${data.departures.length ? data.departures.map((d)=>`<div class="departure-row"><div><strong class="time">${escapeHtml(d.scheduled || '—')}</strong><small>${d.cancelled ? 'Cancelled' : d.expected && d.expected !== d.scheduled ? `Expected ${escapeHtml(d.expected)}` : 'On time / no update'}</small></div><div><strong>${escapeHtml(d.destination)}</strong><small>${escapeHtml(d.operator || 'Rail service')}</small></div><span>${d.cancelled ? 'Cancelled' : d.platform ? `Plat ${escapeHtml(d.platform)}` : 'Platform —'}</span></div>`).join('') : '<div class="empty-state"><strong>No departures returned</strong></div>'}`;
  } catch (error) {
    errorBox.textContent = error.message; errorBox.classList.remove('hidden');
  }
}

function setupGlobe() {
  const canvas = $('globe');
  const ctx = canvas.getContext('2d');
  const resize = () => { const rect = canvas.getBoundingClientRect(); canvas.width = Math.max(1, Math.floor(rect.width * devicePixelRatio)); canvas.height = Math.max(1, Math.floor(rect.height * devicePixelRatio)); };
  new ResizeObserver(resize).observe(canvas); resize();

  canvas.addEventListener('pointerdown', (event) => { state.dragging = true; state.lastX = event.clientX; state.lastY = event.clientY; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener('pointermove', (event) => { if (!state.dragging) return; state.yaw += (event.clientX-state.lastX)*.006; state.pitch = Math.max(-1.25,Math.min(1.25,state.pitch+(event.clientY-state.lastY)*.004)); state.lastX=event.clientX; state.lastY=event.clientY; });
  canvas.addEventListener('pointerup', () => { state.dragging = false; });
  canvas.addEventListener('wheel', (event) => { event.preventDefault(); state.scale=Math.max(.75,Math.min(1.35,state.scale-event.deltaY*.0006)); }, {passive:false});

  const line = (points, color, width, alpha=1) => {
    ctx.beginPath(); let started=false;
    for (const raw of points) {
      const p = projectPoint(rotatePoint(raw,state.yaw,state.pitch),canvas.width,canvas.height,state.scale);
      if (!p.visible) { started=false; continue; }
      if (!started) { ctx.moveTo(p.x,p.y); started=true; } else ctx.lineTo(p.x,p.y);
    }
    ctx.strokeStyle=color; ctx.globalAlpha=alpha; ctx.lineWidth=width*devicePixelRatio; ctx.stroke(); ctx.globalAlpha=1;
  };

  const draw = () => {
    const w=canvas.width,h=canvas.height; ctx.clearRect(0,0,w,h);
    const r=Math.min(w,h)*.38*state.scale,cx=w/2,cy=h/2;
    const gradient=ctx.createRadialGradient(cx-r*.32,cy-r*.28,r*.08,cx,cy,r); gradient.addColorStop(0,'#17475f');gradient.addColorStop(.56,'#0a1d28');gradient.addColorStop(1,'#061017');
    ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fillStyle=gradient;ctx.fill();ctx.strokeStyle='rgba(110,220,238,.17)';ctx.lineWidth=devicePixelRatio;ctx.stroke();

    for (let lat=-60;lat<=60;lat+=30){ const pts=[];for(let lon=-180;lon<=180;lon+=6)pts.push(latLonToXYZ(lat,lon,1.002));line(pts,'#6ddced',.45,.12); }
    for (let lon=-150;lon<=180;lon+=30){ const pts=[];for(let lat=-88;lat<=88;lat+=4)pts.push(latLonToXYZ(lat,lon,1.002));line(pts,'#6ddced',.45,.12); }

    for (const path of state.network.slice(0,100)) {
      const points=(path.points||[]).filter((_,i)=>i%Math.max(1,Math.ceil(path.points.length/90))===0).map((p)=>latLonToXYZ(p.lat,p.lon,1.008));
      if(points.length>1) line(points,path.color||'#6ee7ff',.75,.58);
    }
    if (state.journey) {
      for (const leg of state.journey.legs || []) {
        if (leg.origin?.lat == null || leg.origin?.lon == null || leg.destination?.lat == null || leg.destination?.lon == null) continue;
        line(greatCircleArc(leg.origin,leg.destination,54,.2),leg.mode==='flight'?'#76e9fa':'#7ce5b8',2.15,.98);
      }
    }
    if (!state.dragging) state.yaw += .00055;
    requestAnimationFrame(draw);
  };
  requestAnimationFrame(draw);
}

$('search-form').addEventListener('submit',(event)=>{event.preventDefault();runSearch(false);});
$('sample-search').addEventListener('click',()=>runSearch(true));
$('swap').addEventListener('click',()=>{const a=$('origin').value;$('origin').value=$('destination').value;$('destination').value=a;updateSearchMode();});
$('load-departures').addEventListener('click',loadDepartures);
$('refresh-providers').addEventListener('click',loadProviders);
$('origin').addEventListener('input',(e)=>{e.target.value=e.target.value.toUpperCase();updateSearchMode();});
$('destination').addEventListener('input',(e)=>{e.target.value=e.target.value.toUpperCase();updateSearchMode();});
$('station').addEventListener('input',(e)=>e.target.value=e.target.value.toUpperCase());

setDefaultDate();setupGlobe();loadProviders();
