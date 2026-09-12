/* 서울 가로수길 — 프론트 로직.
   화면은 figma/서울 벚꽃길 추천 시스템/src/App.tsx 를 그대로 옮긴 것이다.
   시안이 하드코딩으로 들고 있던 것(경로 8개·그루 수·4~5점짜리 폴리라인)은 쓰지 않고,
   정본 backend의 /ui/* 읽기 모델과 /chat SSE에서 받는다 — 폴리라인은 실제 나무
   좌표에서 접은 중심선이다.

   시안과 다르게 한 곳(의도적):
     - 나무 그림은 시안처럼 선 위에 흩뿌리지 않고 '실제 나무 좌표'에 놓는다.
       그림은 시안 것 그대로(trees.js), 위치만 원자료다.
     - 배율에 따라 겹치지 않을 만큼만 남긴다. 확대하면 나무가 늘어난다.
     - Leaflet 기본 attribution 컨트롤은 끄고 시안의 우하단 문구를 쓴다
       (시안은 둘 다 켜 두어 서로 겹쳤다). */

const SEASON_TAG = {
  spring:    { label: '봄',     color: '#e91e8c' },
  summer:    { label: '여름',   color: '#2d6a4f' },
  autumn:    { label: '가을',   color: '#e76900' },
  winter:    { label: '겨울',   color: '#1565c0' },
};

const SEASON_BG = {
  spring:    'linear-gradient(160deg,#fce4ec 0%,#fdf6fa 60%,#e8f5e9 100%)',
  summer:    'linear-gradient(160deg,#e8f5e9 0%,#f1f8f4 60%,#e3f2fd 100%)',
  autumn:    'linear-gradient(160deg,#fff8e1 0%,#fffdf5 60%,#fbe9e7 100%)',
  winter:    'linear-gradient(160deg,#e3f2fd 0%,#f5f8ff 60%,#ede7f6 100%)',
  idle:      'linear-gradient(160deg,#f5f3ef 0%,#fafaf8 60%,#eef5ef 100%)',
};

const SEASON_ORDER = ['spring', 'summer', 'autumn', 'winter'];

const QUICK_CHIPS = [
  { label: '🌸 벚꽃 봄산책',     q: '벚꽃길 추천해줘' },
  { label: '🌳 여름 그늘길',     q: '여름 그늘 시원한 길' },
  { label: '🟡 가을 은행 단풍',  q: '가을 은행 단풍길' },
  { label: '❄️ 이팝 흰꽃길',     q: '이팝나무 흰꽃길' },
  { label: '🌲 메타세쿼이아',    q: '메타세쿼이아 이국길' },
  { label: '🍂 은행 냄새 회피',  q: '은행 냄새 회피 경로' },
];

const WELCOME =
  '안녕하세요! 🌿 **서울 가로수 산책길 안내 시스템**입니다.\n\n' +
  '계절이나 원하는 분위기를 입력하시면 지도에 경로를 표시해드립니다.\n\n' +
  '- 봄 벚꽃길 추천해줘\n- 여름에 그늘 많고 시원한 길\n' +
  '- 가을 은행나무 단풍길\n- 메타세쿼이아 이국적인 터널길';

const state = { routes: [], active: [], hoverId: null, busy: false,
  threadId: localStorage.getItem('rushhour-thread-id') || null };
const byId = (id) => document.getElementById(id);
const nf = (n) => Number(n).toLocaleString('ko-KR');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ── 지도 ─────────────────────────────────────────────────── */
const map = L.map('map', { zoomControl: false, attributionControl: false })
  .setView([37.5326, 127.024], 12);
L.control.zoom({ position: 'topright' }).addTo(map);

/* 밑그림 고르기 — 도보 앱이라 z17~19에서 골목·보도가 보여야 한다(DP21).
   · 시안의 CARTO Positron(light_all): 키 없이 부르면 'API KEY REQUIRED' 워터마크.
   · 그다음 쓰던 Esri Light Gray Canvas: 서울 상세 데이터가 없어 **z16부터**
     'Map data not yet available' 회색 타일이 온다 — 확대하면 지도가 사라진다(실측).
   · OSM 표준 타일: 한글 도로명·건물까지 z19로 나오고 키가 필요 없다.
   색이 진해 경로 선을 덮으므로, 밝은 밑그림은 styles.css의 회색 필터로 만든다.
   필터는 tilePane에만 걸리므로 경로 선·마커 색은 그대로다(시안 의도 유지).
   ※ 대량 트래픽이 되면 OSM 타일 정책상 자체 타일 서버나 키 있는 제공자로 옮길 것. */
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

const restLayer = L.layerGroup().addTo(map);    // 켜지지 않은 경로(회색 점선)
const activeLayer = L.layerGroup().addTo(map);  // 켜진 경로
const treeLayer = L.layerGroup().addTo(map);

const isActive = (r) => state.active.some((a) => a.id === r.id);

/** 시안의 Polyline pathOptions 그대로. 비활성은 얇은 회색 점선으로 남는다. */
function lineStyle(r, on) {
  return {
    color: on ? r.color : '#c0bdb7',
    weight: on ? (state.hoverId === r.id ? 7 : 5) : 2,
    opacity: on ? 0.55 : 0.25,
    lineCap: 'round', lineJoin: 'round',
    dashArray: on ? null : '4 6',
  };
}

function bindRoute(pl, r) {
  pl.on('mouseover', () => setHover(r.id));
  pl.on('mouseout', () => setHover(null));
  pl.on('click', () => sendQuery(r.name + ' 추천해줘'));
}

/** 켜진 경로만 굵기를 바꾸면 되므로 다시 그리지 않는다(호버가 끊기지 않게). */
function setHover(id) {
  state.hoverId = id;
  state.active.forEach((r) => (r._lines || []).forEach((pl) => pl.setStyle(lineStyle(r, true))));
}

/* 켜진 경로는 state.active가 들고 있는 paths로 그린다. 에이전트가 자치구를
   집어낸 답변이면 정본 backend의 UI DTO가 그 구 단위 경로를 준다. */
function drawLines() {
  restLayer.clearLayers();
  activeLayer.clearLayers();
  state.routes.forEach((r) => {
    r._lines = [];
    if (isActive(r)) return;
    (r.paths || []).forEach((path) => {
      const pl = L.polyline(path, lineStyle(r, false)).addTo(restLayer);
      bindRoute(pl, r);
      r._lines.push(pl);
    });
  });
  state.active.forEach((r) => {
    r._lines = [];
    (r.paths || []).forEach((path) => {
      const pl = L.polyline(path, lineStyle(r, true)).addTo(activeLayer);
      bindRoute(pl, r);
      // 시안은 활성 경로에만 툴팁을 붙인다.
      pl.bindTooltip(`${r.emoji} ${r.name} — ${(r.roads || []).join(', ')}`,
        { sticky: true, className: 'route-tooltip', offset: [0, -10] });
      r._lines.push(pl);
    });
  });
}

/** 화면에 보이는 것 중, 서로 겹치지 않을 만큼만 남긴 나무 좌표. */
function visibleTrees(points, cap) {
  const zoom = map.getZoom();
  const bounds = map.getBounds().pad(0.1);
  const seen = new Set();
  const out = [];
  for (const [lat, lng] of points) {
    if (!bounds.contains([lat, lng])) continue;
    const p = map.project([lat, lng], zoom);
    const key = Math.round(p.x / 46) + ',' + Math.round(p.y / 46);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([lat, lng]);
    if (out.length >= cap) break;
  }
  return out;
}

function drawTrees() {
  treeLayer.clearLayers();
  const cap = Math.max(30, Math.floor(170 / Math.max(1, state.active.length)));
  state.active.forEach((r) => {
    if (!r.points) return;
    visibleTrees(r.points, cap).forEach(([lat, lng], i) => {
      L.marker([lat, lng], { icon: treeIcon(r.id, (i * 7) % 10), interactive: false })
        .addTo(treeLayer);
    });
  });
}

function flyToActive() {
  const pts = state.active.flatMap((r) => (r.paths || []).flat());
  if (!pts.length) return;
  map.flyToBounds(L.latLngBounds(pts), { padding: [80, 80], duration: 1.4, maxZoom: 15 });
}

map.on('zoomend moveend', drawTrees);

/* ── 렌더 ─────────────────────────────────────────────────── */
const currentSeason = () => (state.active[0] ? state.active[0].season : 'idle');

function renderSeasons() {
  const now = currentSeason();
  byId('seasons').innerHTML = SEASON_ORDER.map((s) => {
    const t = SEASON_TAG[s];
    const on = now === s;
    return `<span data-active="${on}"${on ? ` style="background:${t.color}"` : ''}>${t.label}</span>`;
  }).join('');
}

function renderList() {
  byId('themelist').innerHTML = state.routes.map((r) => {
    const on = isActive(r);
    const tag = SEASON_TAG[r.season] || SEASON_TAG.spring;
    return `<button class="trow" data-id="${r.id}" aria-pressed="${on}"
      style="--line:${r.color};--tint:${r.color}12">
      <span class="emoji">${r.emoji}</span>
      <span class="txt">
        <span class="nm">${esc(r.name)}</span>
        <span class="meta">
          <span class="badge" style="color:${tag.color};background:${tag.color}18">${tag.label}</span>
          <span class="gu">${esc(r.district)}</span>
        </span>
      </span>
      ${on ? '<span class="dot"></span>' : ''}
    </button>`;
  }).join('');
}

function renderChips() {
  byId('chips').innerHTML = QUICK_CHIPS.map((c, i) =>
    `<button data-i="${i}">${c.label}</button>`).join('');
}

function renderLegend() {
  const el = byId('legend');
  if (!state.active.length) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<h4>표시된 경로 (${state.active.length})</h4>` +
    state.active.map((r) => `<div class="row">
      <div class="bar" style="background:${r.color}"></div>
      <span>${r.emoji} ${esc(r.name)}</span></div>`).join('');
}

function applySeason() {
  byId('chatpanel').style.background = SEASON_BG[currentSeason()] || SEASON_BG.idle;
}

/* ── 챗 ───────────────────────────────────────────────────── */
/** 답변에 오는 얕은 마크다운만 처리한다(**굵게**, _흐림_, 줄바꿈, - 목록). */
function md(text) {
  return esc(text).split(/\n{2,}/).map((block) => {
    const lines = block.split('\n');
    if (lines.every((l) => /^\s*[-•]\s+/.test(l))) {
      return `<ul>${lines.map((l) => `<li>${inline(l.replace(/^\s*[-•]\s+/, ''))}</li>`).join('')}</ul>`;
    }
    return `<p>${lines.map(inline).join('<br>')}</p>`;
  }).join('');
}
function inline(s) {
  return s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
          .replace(/_(.+?)_/g, '<em>$1</em>');
}

function cardsHtml(routes) {
  if (!routes || !routes.length) return '';
  return `<div class="cards">` + routes.map((r) => `
    <button class="card" data-id="${r.id}"
      style="--line15:${r.color}15;--line28:${r.color}28;--line44:${r.color}44">
      <span class="emoji">${r.emoji}</span>
      <span class="txt">
        <span class="nm">${esc(r.name)}</span>
        <span class="sub">${esc(r.district)} · ${esc(r.seasonLabel)} · ${nf(r.treeCount)}그루</span>
      </span>
      <span class="dot" style="background:${r.color}"></span>
    </button>`).join('') + `</div>`;
}

function bubble(role, text, routes) {
  const el = document.createElement('div');
  el.className = 'msg' + (role === 'user' ? ' me' : '');
  const body = `<div class="bub">${md(text)}${role === 'user' ? '' : cardsHtml(routes)}</div>`;
  el.innerHTML = role === 'user' ? body : `<div class="av">🌿</div>${body}`;
  byId('chatlog').appendChild(el);
  scrollChat();
  return el;
}

function typingBubble() {
  const el = document.createElement('div');
  el.className = 'msg typing';
  el.innerHTML = '<div class="av">🌿</div><div class="bub"><i></i><i></i><i></i></div>';
  byId('chatlog').appendChild(el);
  scrollChat();
  return el;
}

function scrollChat() {
  const log = byId('chatlog');
  log.scrollTo({ top: log.scrollHeight, behavior: 'smooth' });
}

/* ── 상태 전환 ────────────────────────────────────────────── */
/** SSE final의 ui_routes. 자치구로 좁혀진 paths·points가 실려 올 수 있다. */
async function setActive(briefs) {
  state.active = (briefs || []).map((b) => {
    const base = state.routes.find((x) => x.id === b.id) || {};
    return Object.assign({}, base, b, { _lines: [] });   // 좁힌 쪽이 전역을 덮는다
  });
  state.hoverId = null;
  renderSeasons(); renderList(); renderLegend(); applySeason(); drawLines();
  flyToActive();
  // 나무 좌표는 서울 전역 답변일 때만 따로 받아 온다(좁힌 답변은 이미 실려 왔다).
  await Promise.all(state.active.map(async (r) => {
    if (r.points) return;
    try {
      const cached = state.routes.find((x) => x.id === r.id);
      if (cached && cached.points) { r.points = cached.points; return; }
      const d = await (await fetch(`/ui/theme/${r.id}`)).json();
      r.points = d.points || [];
      if (cached) cached.points = r.points;             // 다음 턴을 위해 캐시
    } catch { r.points = []; }
  }));
  drawTrees();
}

async function sendQuery(q) {
  if (state.busy) return;
  state.busy = true;
  bubble('user', q);
  const wait = typingBubble();
  try {
    const res = await fetch('/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: q, thread_id: state.threadId }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const r = await readSse(res);
    wait.remove();
    bubble('assistant', r.final_answer || '(답변 없음)', r.ui_routes || []);
    await setActive(r.ui_routes || []);
  } catch (e) {
    wait.remove();
    bubble('assistant', `요청이 실패했습니다: ${e.name}. 서버 상태를 확인해 주세요.`);
  }
  state.busy = false;
}

async function readSse(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', final = null;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const events = buffer.split('\n\n');
    buffer = events.pop();
    for (const raw of events) {
      const type = (raw.match(/^event: (.+)$/m) || [])[1];
      const json = (raw.match(/^data: (.+)$/m) || [])[1];
      if (!json) continue;
      const data = JSON.parse(json);
      if (type === 'start' && data.thread_id) {
        state.threadId = data.thread_id;
        localStorage.setItem('rushhour-thread-id', data.thread_id);
      }
      if (type === 'final') final = data;
      if (type === 'error') throw new Error(data.message || '서버 오류');
    }
    if (done) break;
  }
  if (!final) throw new Error('final SSE 이벤트 없음');
  return final;
}

/* ── 이벤트 ───────────────────────────────────────────────── */
byId('themelist').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-id]'); if (!b) return;
  const r = state.routes.find((x) => x.id === b.dataset.id);
  if (r) sendQuery(r.name + ' 추천해줘');
});
byId('chips').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-i]'); if (!b) return;
  sendQuery(QUICK_CHIPS[+b.dataset.i].q);
});
byId('chatlog').addEventListener('click', (e) => {
  const b = e.target.closest('.card'); if (!b) return;
  const r = state.routes.find((x) => x.id === b.dataset.id);
  if (r) sendQuery(r.name + ' 더 자세히 알려줘');
});
byId('q').addEventListener('input', (e) => {
  byId('send').disabled = !e.target.value.trim();
});
byId('chatform').addEventListener('submit', (e) => {
  e.preventDefault();
  const v = byId('q').value.trim(); if (!v) return;
  byId('q').value = '';
  byId('send').disabled = true;
  sendQuery(v);
});

/* ── 시작 ─────────────────────────────────────────────────── */
(async function boot() {
  const o = await (await fetch('/ui/overview')).json();
  state.routes = o.themes;

  byId('stats').innerHTML =
    `<div><b>${o.totals.themes}</b><span>테마 경로</span></div>` +
    `<div><b>${nf(o.totals.trees)}</b><span>가로수 총계</span></div>` +
    `<div><b>${o.totals.districts}</b><span>커버 구</span></div>`;

  renderSeasons(); renderList(); renderChips(); applySeason();
  drawLines();
  byId('boot').hidden = true;

  // 시안과 같이 경로를 하나도 켜지 않은 상태에서 인사말로 시작한다.
  bubble('assistant', WELCOME);
})();
