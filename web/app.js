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
  allseason: { label: '사계절', color: '#546e7a' },
};

const SEASON_BG = {
  spring:    'linear-gradient(160deg,#fce4ec 0%,#fdf6fa 60%,#e8f5e9 100%)',
  summer:    'linear-gradient(160deg,#e8f5e9 0%,#f1f8f4 60%,#e3f2fd 100%)',
  autumn:    'linear-gradient(160deg,#fff8e1 0%,#fffdf5 60%,#fbe9e7 100%)',
  winter:    'linear-gradient(160deg,#e3f2fd 0%,#f5f8ff 60%,#ede7f6 100%)',
  allseason: 'linear-gradient(160deg,#f5f3ef 0%,#fafaf8 60%,#eef5ef 100%)',
};

/* 시안(figma2)은 계절 탭·좌측 목록 모두 봄→여름→가을→겨울→사계절 순이다.
   경로가 하나도 켜지지 않은 상태는 '사계절'로 본다(App.tsx currentSeason). */
const SEASON_ORDER = ['spring', 'summer', 'autumn', 'winter', 'allseason'];

/* 시안(figma2)의 8개 그대로 — 백엔드 THEMES에 크리스마스·상록이 추가돼 전부 답할 수 있다. */
const QUICK_CHIPS = [   // id: 클릭 즉시 흩뿌릴 테마(effects.js)
  { label: '🌸 벚꽃 봄산책',     q: '벚꽃길 추천해줘',      id: 'cherry' },
  { label: '🌳 여름 그늘길',     q: '여름 그늘 시원한 길',   id: 'shade' },
  { label: '🍂 가을 은행 단풍',  q: '가을 은행 단풍길',      id: 'ginkgo-enjoy' },
  { label: '✿ 이팝 흰꽃길',      q: '이팝나무 흰꽃길',       id: 'ipaeb' },
  { label: '🌲 메타세쿼이아',    q: '메타세쿼이아 이국길',   id: 'metasequoia' },
  { label: '🎄 크리스마스 축제', q: '크리스마스 축제길',     id: 'christmas' },
  { label: '🌿 상록 소나무',     q: '사철 상록 소나무길',    id: 'evergreen' },
  { label: '🟡 은행 열매 피하기', q: '은행 열매 밟지 않는 길', id: 'ginkgo-avoid' },
];

const WELCOME =
  '안녕하세요! 🌿 **그루그루**입니다.\n\n' +
  '계절이나 원하는 분위기를 입력하시면 지도에 경로를 표시해드립니다.\n\n' +
  '- 봄 벚꽃길 추천해줘\n- 여름에 그늘 많고 시원한 길\n' +
  '- 가을 은행나무 단풍길\n- 메타세쿼이아 이국적인 터널길';

const state = { routes: [], active: [], hoverId: null, busy: false,
  threadId: localStorage.getItem('rushhour-thread-id') || null };
const byId = (id) => document.getElementById(id);
const nf = (n) => Number(n).toLocaleString('ko-KR');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* figma2 시안이 바꾼 표현 — 이모지(이팝 ✿ · 은행 열매 밟지 않는 길 🟡 · 은행 단풍 🍂)와
   '사계' 테마의 사계절 그룹 배치. 백엔드 DTO(web_ui.PRESENTATION)는 두고 화면에서 입힌다. */
const EMOJI = { ipaeb: '✿', 'ginkgo-avoid': '🟡', 'ginkgo-enjoy': '🍂' };
function decorate(r) {
  if (EMOJI[r.id]) r.emoji = EMOJI[r.id];
  if (/사계/.test(r.seasonLabel || '')) r.season = 'allseason';
  return r;
}
const emojiClass = (r) => 'emoji' + (r.id === 'ipaeb' ? ' ipaeb' : '');

/* ── 나무 그리기(DP24) ──────────────────────────────────────
   두 갈래 자료를 같은 나무 그림으로 그린다.
     ① 가로수 대장  — 나무 한 그루마다 좌표가 있다. 그 테마 **전부**를 받는다(벚꽃 31,550그루).
        상위 6개 도로만 받던 때는 석촌호수처럼 순위 밖의 길이 지도에서 사라졌다.
     ② 공공자료 합본 — 노선당 대표점 하나뿐이다(공원·하천·전국). 한 그루처럼 보이면 안 되므로
        그루수를 툴팁에 적고 크기를 키운다.
   화면에 보이는 것만, 46px 격자로 솎아 그린다(visibleTrees) — 수천 개를 다 그리면 지도가 멈춘다. */
const themePtCache = {};        // 테마별 가로수 대장 좌표
const spotCache = {};           // 테마별 합본 점

async function fetchJSON(url) {
  try { return await (await fetch(url)).json(); } catch { return null; }
}

async function loadThemeTrees(theme) {
  if (themePtCache[theme] === undefined) {
    const d = await fetchJSON(`/map/theme_points?theme=${encodeURIComponent(theme)}`);
    themePtCache[theme] = d?.points || [];
  }
  return themePtCache[theme];
}

async function loadSpots(theme) {
  const key = theme || '';
  if (spotCache[key] === undefined) {
    const d = await fetchJSON(`/spots/points${key ? `?theme=${encodeURIComponent(key)}` : ''}`);
    spotCache[key] = d?.ok ? d.points : [];
  }
  return spotCache[key];
}

/* 한 노선을 대표하는 구간. 실제 도로 형상이 있으면 그것을, 없으면 시작~종료 두 점을 쓴다.
   두 점이 너무 멀면(5km 초과) 직선이 실제 길과 크게 어긋나므로 쓰지 않는다. */
function pickSegment(s) {
  if (s.path && s.path.length) return s.path.reduce((a, b) => (a.length >= b.length ? a : b));
  if (!s.se) return null;
  const [a, b] = s.se;
  const km = Math.hypot((a[0] - b[0]) * 111.32, (a[1] - b[1]) * 88.8);
  return km > 0.02 && km < 5 ? s.se : null;
}

/* 구간을 따라 n개를 고르게 — 길이에 비례해 나눠 짚고, 길 양옆으로 번갈아 세운다.
   가로수는 길 가장자리에 줄지어 서 있다. 중심선 위에 겹쳐 찍으면 한 줄로 뭉쳐 보인다. */
const SIDE_M = 0.011;                       // 중심선에서 약 11m — 인도 폭 정도

function spreadAlong(line, n) {
  if (line.length < 2) return [line[0]];
  const seg = [];
  let total = 0;
  for (let i = 1; i < line.length; i += 1) {
    const d = Math.hypot((line[i][0] - line[i - 1][0]) * 111.32,
                         (line[i][1] - line[i - 1][1]) * 88.8);
    seg.push(d); total += d;
  }
  if (!total) return [line[0]];
  const out = [];
  for (let k = 0; k < n; k += 1) {
    let want = (total * (k + 0.5)) / n;
    for (let i = 0; i < seg.length; i += 1) {
      if (want <= seg[i] || i === seg.length - 1) {
        const t = seg[i] ? Math.min(1, want / seg[i]) : 0;
        const lat = line[i][0] + (line[i + 1][0] - line[i][0]) * t;
        const lng = line[i][1] + (line[i + 1][1] - line[i][1]) * t;
        // 그 토막의 방향을 90° 돌려 좌·우로 번갈아 — 길을 낀 가로수 줄처럼 보이게
        const dy = (line[i + 1][0] - line[i][0]) * 111.32;
        const dx = (line[i + 1][1] - line[i][1]) * 88.8;
        const len = Math.hypot(dy, dx) || 1;
        const side = k % 2 ? 1 : -1;
        out.push([lat + (side * SIDE_M * -dx) / len / 111.32,
                  lng + (side * SIDE_M * dy) / len / 88.8]);
        break;
      }
      want -= seg[i];
    }
  }
  return out;
}

function lineKm(line) {
  let km = 0;
  for (let i = 1; i < line.length; i += 1) {
    km += Math.hypot((line[i][0] - line[i - 1][0]) * 111.32,
                     (line[i][1] - line[i - 1][1]) * 88.8);
  }
  return km;
}

/* 화면에 걸치는 부분만 남긴다. 3km짜리 길에 나무 몇 그루를 고르게 흩으면, 확대했을 때
   대부분이 화면 밖에 떨어져 눈앞의 길은 텅 빈다 — 보이는 토막에 몰아 줘야 줄지어 보인다. */
function clipLine(line, bounds) {
  let lo = -1;
  let hi = -1;
  for (let i = 0; i < line.length; i += 1) {
    if (bounds.contains(line[i])) { if (lo < 0) lo = i; hi = i; }
  }
  if (lo < 0) return line;                                  // 다 밖이면 통째로
  const a = Math.max(0, lo - 1);                            // 화면 경계를 넘어 한 점씩
  const b = Math.min(line.length - 1, hi + 1);
  return b - a >= 1 ? line.slice(a, b + 1) : line;
}

/* 몇 그루를 그릴지는 **줌**이 정한다. 나무 그림 사이가 화면에서 늘 비슷하게 떨어지도록
   목표 간격을 픽셀로 잡고 미터로 환산한다 — 확대하면 촘촘해지고, 축소하면 한 노선 한 그루가 된다.
   예전에는 그루수만 봐서(√c/6) 63그루짜리가 어느 줌에서든 **한 그루**로 그려졌다.
   아는 그루수보다 많이 그리지는 않는다 — 6그루 길에 20그루를 세울 수는 없다. */
function treeCount(s, line) {
  const mPerPx = (156543.03 * Math.cos((map.getCenter().lat * Math.PI) / 180))
                 / 2 ** map.getZoom();
  const gapKm = (mPerPx * 58) / 1000;                       // 아이콘 하나 반쯤 띄운 간격
  const n = Math.round(lineKm(line) / gapKm);
  const known = s.c === null || s.c === undefined ? 26 : Math.max(1, s.c);
  return Math.max(1, Math.min(26, n, known));
}

/* 켠 테마에 맞는 나무를 받아 둔다. 토글은 두지 않는다 — 물은 것만 보여 주면 된다. */
async function refreshSpots() {
  const known = new Set(state.routes.map((r) => r.key));
  await Promise.all(state.active.map(async (r) => {
    const theme = known.has(r.key) ? r.key : '';
    if (!theme) { r._spots = []; r._all = []; return; }
    [r._all, r._spots] = await Promise.all([loadThemeTrees(theme), loadSpots(theme)]);
  }));
  drawTrees();
}

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
const spotLayer = L.layerGroup();               // 공공자료 합본의 나무 — 켠 테마를 따라간다

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

/* 칸 수만큼의 격자가 화면을 덮도록 한 칸의 크기(위도·경도)를 정한다.
   화면에서 정사각형이 되게 — 경도 1도는 위도 1도보다 좁다(서울에서 약 0.79배). */
function cellSpan(cells) {
  const b = map.getBounds();
  const dy = b.getNorth() - b.getSouth();
  const dx = b.getEast() - b.getWest();
  const aspect = Math.max(0.2, (dx * Math.cos((map.getCenter().lat * Math.PI) / 180)) / dy);
  const rows = Math.max(1, Math.sqrt(cells / aspect));
  return [dy / rows, dx / Math.max(1, cells / rows)];
}

/* 격자 칸을 흩어진 순서로 — 가까운 것부터 예산껏 그리면 가운데만 뭉치고 가장자리가 빈다.
   칸 번호를 섞어 정렬하면 예산이 어디서 끊기든 화면 전체에 고르게 남는다. */
function scatterKey(gy, gx) {
  const h = Math.imul(gy + 1, 0x9e3779b1) ^ Math.imul(gx + 1, 0x85ebca6b);
  return (h >>> 0) % 100000;
}

function drawTrees() {
  treeLayer.clearLayers();
  spotLayer.clearLayers();
  const n = Math.max(1, state.active.length);
  const cap = Math.max(40, Math.floor(420 / n));
  state.active.forEach((r) => {
    // ① 가로수 대장 — 그 테마 전부에서 화면에 보이는 것만. 좁힌 답변이면 그 점을 먼저 쓴다.
    const pool = (r.points && r.points.length ? r.points : null) || r._all || [];
    visibleTrees(pool, cap).forEach(([lat, lng], i) => {
      L.marker([lat, lng], { icon: treeIcon(r.id, (i * 7) % 10), interactive: false })
        .addTo(treeLayer);
    });
    // ② 합본 — 대장에 없는 공원·하천·전국. 좌표가 노선당 한 점뿐이라 한 그루처럼 보이므로,
    //    아는 구간(실제 도로 형상 또는 시작~종료)을 따라 흩뿌린다. 개별 나무 위치를 아는 게
    //    아니라 '이 구간에 이만큼 있다'는 표시다 — 툴팁에 그루수와 출처를 적는다.
    const spots = r._spots || [];
    const bounds = map.getBounds().pad(0.15);
    const ctr = map.getCenter();
    const near = spots
      .filter((s) => bounds.contains(s.ll))
      .sort((a, b) => ((a.ll[0] - ctr.lat) ** 2 + (a.ll[1] - ctr.lng) ** 2)
                    - ((b.ll[0] - ctr.lat) ** 2 + (b.ll[1] - ctr.lng) ** 2));
    // 그림 수로 예산을 잡는다 — 노선 수로 자르면 긴 노선 몇 개가 예산을 다 먹는다.
    let budget = Math.max(260, Math.floor(900 / n));
    // 다 들어가면 솎지 않는다. 축소해서 화면에 수천 개가 걸릴 때만 격자로 고르게 고른다 —
    // 확대했을 때까지 솎으면 노선 두 개뿐인 여의도가 나무 네 그루가 된다.
    const thin = near.length > budget;
    const cell = cellSpan(budget * 2.2);
    const taken = new Set();
    if (thin) {
      near.forEach((s) => {
        s._cell = [Math.round(s.ll[0] / cell[0]), Math.round(s.ll[1] / cell[1])];
      });
      near.sort((a, b) => scatterKey(...a._cell) - scatterKey(...b._cell));
    }
    near.forEach((s, si) => {
      if (budget <= 0) return;
      if (thin) {
        const key = `${s._cell[0]},${s._cell[1]}`;
        if (taken.has(key)) return;
        taken.add(key);
      }
      const line = pickSegment(s);
      const seen = line ? clipLine(line, bounds) : null;
      const spread = (seen ? spreadAlong(seen, treeCount(s, seen)) : [s.ll]).slice(0, budget);
      budget -= spread.length;
      const big = s.c && s.c > 800;
      spread.forEach((ll, i) => {
        L.marker(ll, { icon: treeIcon(r.id, (si * 3 + i * 5) % 10, big && i === 0 ? 46 : 34) })
          .bindTooltip(`${esc(s.n)} · ${esc(s.k)} · ${s.c === null ? '그루수 미기재' : nf(s.c) + '그루'}`
                       + `<br><span style="opacity:.65">${esc(s.g)} · 출처 ${esc(s.src)}</span>`)
          .addTo(spotLayer);
      });
    });
  });
  spotLayer.addTo(map);
}

function flyToActive() {
  const pts = state.active.flatMap((r) => (r.paths || []).flat());
  if (!pts.length) return;
  map.flyToBounds(L.latLngBounds(pts), { padding: [80, 80], duration: 1.4, maxZoom: 15 });
}

map.on('zoomend moveend', drawTrees);

/* ── 렌더 ─────────────────────────────────────────────────── */
const currentSeason = () => (state.active[0] ? state.active[0].season : 'allseason');

function renderSeasons() {
  const now = currentSeason();
  byId('seasons').innerHTML = SEASON_ORDER.map((s) => {
    const t = SEASON_TAG[s];
    const on = now === s;
    return `<span data-active="${on}"${on ? ` style="background:${t.color}"` : ''}>${t.label}</span>`;
  }).join('');
}

/* 시안(figma2)의 ROUTE_GROUPS — 계절별 소제목 아래 묶는다. 시안은 id를 박아 두었지만
   여기서는 백엔드가 준 season으로 묶고, 비어 있는 계절(겨울 등)은 소제목을 내지 않는다. */
function renderList() {
  byId('themelist').innerHTML = SEASON_ORDER.map((s) => {
    const rows = state.routes.filter((r) => (r.season || 'allseason') === s);
    if (!rows.length) return '';
    const tag = SEASON_TAG[s];
    return `<div class="tgroup">
      <div class="tgroup-title" style="color:${tag.color}">${tag.label}</div>
      ${rows.map(themeRow).join('')}
    </div>`;
  }).join('');
}

function themeRow(r) {
  const on = isActive(r);
  const tag = SEASON_TAG[r.season] || SEASON_TAG.allseason;
  return `<button class="trow" data-id="${r.id}" aria-pressed="${on}"
    style="--line:${r.color};--tint:${r.color}12">
    <span class="${emojiClass(r)}">${r.emoji}</span>
    <span class="txt">
      <span class="nm">${esc(r.name)}</span>
      <span class="meta">
        <span class="badge" style="color:${tag.color};background:${tag.color}18">${tag.label}</span>
        <span class="gu">${esc(r.district)}</span>
      </span>
    </span>
    ${on ? '<span class="dot"></span>' : ''}
  </button>`;
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
  byId('chatpanel').style.background = SEASON_BG[currentSeason()] || SEASON_BG.allseason;
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
      <span class="${emojiClass(r)}">${r.emoji}</span>
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
    return decorate(Object.assign({}, base, b, { _lines: [] }));   // 좁힌 쪽이 전역을 덮는다
  });
  state.hoverId = null;
  renderSeasons(); renderList(); renderLegend(); applySeason(); drawLines();
  flyToActive();
  // 테마가 켜지는 순간 그 테마의 잎·꽃잎·눈을 한 번 흩뿌린다(effects.js). 경로 3종 등 정의 없는 id는 무시.
  if (state.active[0]) sprinkle(state.active[0].id); else clearSprinkle();
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
  refreshSpots();                 // 나무(대장 전체 + 합본)를 받아 그린다(DP24)
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
/* 테마를 아는 클릭(목록·칩·카드)은 답변을 기다리지 않고 그 자리에서 흩뿌린다 — 답변은 LLM이라
   8초쯤 걸리는데 그때까지 아무 반응이 없으면 안 되는 줄 안다. setActive의 호출은 같은 테마면 건너뛴다. */
byId('themelist').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-id]'); if (!b) return;
  const r = state.routes.find((x) => x.id === b.dataset.id);
  if (!r || state.busy) return;
  sprinkle(r.id);
  sendQuery(r.name + ' 추천해줘');
});
byId('chips').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-i]'); if (!b) return;
  const c = QUICK_CHIPS[+b.dataset.i];
  if (state.busy) return;
  if (c.id) sprinkle(c.id);
  sendQuery(c.q);
});
byId('chatlog').addEventListener('click', (e) => {
  const b = e.target.closest('.card'); if (!b) return;
  const r = state.routes.find((x) => x.id === b.dataset.id);
  if (!r || state.busy) return;
  sprinkle(r.id);
  sendQuery(r.name + ' 더 자세히 알려줘');
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

/* ── 산책길 검색(출발지→목적지) — figma2 시안의 route finder ─────────────
   입력 칸 위의 토글 버튼을 누르면 팝오버가 뜨고, 두 칸을 채워 보내면
   시안과 같은 문장("A에서 B까지 가로수 산책 경로를 찾아줘")으로 /chat에 묻는다. */
const rf = {
  toggle: byId('rf-toggle'), pop: byId('rf-pop'),
  origin: byId('rf-origin'), dest: byId('rf-dest'), send: byId('rf-send'),
};
function rfUpdate() {
  rf.send.disabled = !(rf.origin.value.trim() && rf.dest.value.trim());
}
function rfOpen(open) {
  rf.pop.hidden = !open;
  rf.toggle.setAttribute('aria-expanded', String(open));
  if (open) rf.origin.focus();
}
function rfSend() {
  const a = rf.origin.value.trim(), b = rf.dest.value.trim();
  if (!a || !b) return;
  sendQuery(`${a}에서 ${b}까지 가로수 산책 경로를 찾아줘`);
  rf.origin.value = ''; rf.dest.value = ''; rfUpdate();
  rfOpen(false);
}
rf.toggle.addEventListener('click', () => rfOpen(rf.pop.hidden));
rf.origin.addEventListener('input', rfUpdate);
rf.dest.addEventListener('input', rfUpdate);
rf.dest.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); rfSend(); } });
rf.origin.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); rf.dest.focus(); } });
rf.send.addEventListener('click', rfSend);

/* ── 시작 ─────────────────────────────────────────────────── */
(async function boot() {
  const o = await (await fetch('/ui/overview')).json();
  state.routes = o.themes.map(decorate);

  byId('stats').innerHTML =
    `<div><b>${o.totals.themes}</b><span>테마 경로</span></div>` +
    `<div><b>${nf(o.totals.trees)}</b><span>가로수 총계</span></div>` +
    `<div><b>${o.totals.districts}</b><span>커버 구</span></div>`;

  renderSeasons(); renderList(); renderChips(); applySeason();
  drawLines();
  byId('boot').hidden = true;

  // 공공자료 합본이 준비돼 있을 때만 명소 토글을 보여 준다(DP24).

  // 시안과 같이 경로를 하나도 켜지 않은 상태에서 인사말로 시작한다.
  bubble('assistant', WELCOME);
})();
