/* 테마가 켜질 때 지도 위로 잎·꽃잎·눈을 한 번 흩뿌리는 연출.
   지도 조작을 막지 않게 pointer-events:none 오버레이(#fx)에 DOM 입자를 띄우고
   CSS 애니메이션(styles.css .fx-p)으로 떨어뜨린다. 3~6초 뒤 스스로 사라지고,
   다른 테마로 바뀌면 즉시 치운다. prefers-reduced-motion이면 아무것도 하지 않는다.

   입자 색은 trees.js의 나무 그림과 같은 팔레트를 쓴다(테마마다 화면 톤이 이어지게). */

const PARTICLES = {
  cherry:         { shape: 'petal',  count: 81, colors: ['#f8b4cc', '#f4a8c4', '#fbd0e0', '#f9c0d8'], size: [17, 30], dur: [3.2, 5.5] },
  ipaeb:          { shape: 'petal',  count: 71, colors: ['#ffffff', '#f4fbf5', '#eaf7ec'],          size: [15, 23], dur: [3.5, 6],   stroke: '#74c69d', glow: '#74c69d' },
  shade:          { shape: 'leaf',   count: 44, colors: ['#52b788', '#74c69d', '#40916c'],          size: [22, 35], dur: [4, 7] },
  'ginkgo-enjoy': { shape: 'fan',    count: 71, colors: ['#f9c74f', '#ffe08a', '#fdd166', '#ffe566'], size: [20, 32], dur: [3.5, 6] },
  'ginkgo-avoid': { shape: 'fan',    count: 44, colors: ['#f3c94d', '#e9b949', '#f8da70'],          size: [18, 27], dur: [3.5, 6] },
  metasequoia:    { shape: 'needle', count: 57, colors: ['#74c69d', '#52b788', '#40916c'],          size: [17, 27], dur: [3, 5] },
  christmas:      { shape: 'snow',   count: 108, colors: ['#ffffff', '#eaf4ff', '#dbeafe'],          size: [10, 18],  dur: [5, 9],  glow: '#93c5fd', stroke: '#93c5fd' },
  evergreen:      { shape: 'needle', count: 47, colors: ['#1b4332', '#2d6a4f', '#40916c'],          size: [17, 27], dur: [3.5, 6] },
};

/* 입자 한 개의 SVG. 모양은 5가지 — 꽃잎(타원), 활엽(잎맥 있는 잎), 은행 부채잎, 침엽(가늘고 긴 잎), 눈(원). */
const SHAPES = {
  petal: (c, s, o) =>
    `<svg viewBox="0 0 20 20" width="${s}" height="${s}"><ellipse cx="10" cy="10" rx="9" ry="5.5" fill="${c}"
       ${o.stroke ? `stroke="${o.stroke}" stroke-width="1.3"` : ''} opacity="0.92"/></svg>`,
  leaf: (c, s) =>
    `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><path d="M3 21 C3 9 12 3 21 3 C21 15 12 21 3 21Z" fill="${c}" opacity="0.9"/>
       <path d="M4 20 L19 5" stroke="#1b4332" stroke-width="0.8" opacity="0.35"/></svg>`,
  fan: (c, s) =>
    `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><path d="M12 22 L12 14 C4 14 2 8 3 3 C8 4 11 8 12 12 C13 8 16 4 21 3 C22 8 20 14 12 14Z" fill="${c}" opacity="0.92"/>
       <line x1="12" y1="14" x2="12" y2="22" stroke="#8a6d1f" stroke-width="1" opacity="0.5"/></svg>`,
  needle: (c, s) =>
    `<svg viewBox="0 0 24 24" width="${s}" height="${s}"><path d="M12 2 L14 12 L12 22 L10 12Z" fill="${c}" opacity="0.9"/>
       <path d="M12 6 L18 9 M12 10 L6 13 M12 14 L18 17" stroke="${c}" stroke-width="1.6" stroke-linecap="round" opacity="0.8"/></svg>`,
  snow: (c, s, o) =>
    `<svg viewBox="0 0 20 20" width="${s}" height="${s}"><circle cx="10" cy="10" r="8" fill="${c}"
       ${o.stroke ? `stroke="${o.stroke}" stroke-width="1.2"` : ''} opacity="0.95"/></svg>`,
};

const rnd = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
let fxTimer = null;
let fxCurrent = null;   // 지금 떨어지고 있는 테마 id — 같은 테마를 겹쳐 뿌리지 않게

/** 오버레이를 비운다(테마가 바뀌거나 꺼질 때). */
function clearSprinkle() {
  const box = document.getElementById('fx');
  if (box) box.innerHTML = '';
  if (fxTimer) { clearTimeout(fxTimer); fxTimer = null; }
  fxCurrent = null;
}

/** 테마 id에 맞는 입자를 한 번 흩뿌린다. 정의가 없는 id(경로 3종 등)는 조용히 무시.
    클릭 순간(app.js 이벤트)과 답변 도착(setActive) 두 번 불리는데, 같은 테마가 아직 떨어지는
    중이면 두 번째는 건너뛴다 — 클릭 즉시 반응하고 답변 때 겹쳐 뿌리지 않게. */
function sprinkle(themeId) {
  const spec = PARTICLES[themeId];
  const box = document.getElementById('fx');
  if (!spec || !box) return;
  // OS '동작 줄이기'(Windows 애니메이션 효과 끔 등)면 끄지 않고 절반만·회전 없이 조용히 내린다.
  const reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  if (fxCurrent === themeId && box.childElementCount) return;
  clearSprinkle();
  fxCurrent = themeId;
  const frag = document.createDocumentFragment();
  let longest = 0;
  const count = reduced ? Math.ceil(spec.count / 2) : spec.count;
  for (let i = 0; i < count; i++) {
    const s = Math.round(rnd(spec.size[0], spec.size[1]));
    const dur = rnd(spec.dur[0], spec.dur[1]);
    const delay = rnd(0, 1.6);
    longest = Math.max(longest, dur + delay);
    const p = document.createElement('div');
    p.className = 'fx-p' + (spec.glow ? ' glow' : '');   // glow: 밝은 바탕에서 흰 입자가 묻히지 않게 색 광택
    p.style.cssText =
      `left:${rnd(-2, 100).toFixed(1)}%;` +
      `--dur:${dur.toFixed(2)}s;--delay:${delay.toFixed(2)}s;` +
      `--sway:${rnd(18, 60).toFixed(0)}px;--spin:${(reduced ? 0 : rnd(-540, 540)).toFixed(0)}deg;` +
      `--tilt:${rnd(0, 360).toFixed(0)}deg` + (spec.glow ? `;--glow:${spec.glow}` : '');
    p.innerHTML = `<span>${SHAPES[spec.shape](pick(spec.colors), s, spec)}</span>`;
    frag.appendChild(p);
  }
  box.appendChild(frag);
  fxReport(themeId, count, reduced);
  // 마지막 입자까지 떨어진 뒤 정리. 클래스 토글로 계절 배경도 잠깐 밝혀도 좋지만 지도 위엔 입자만.
  fxTimer = setTimeout(clearSprinkle, (longest + 0.3) * 1000);
}

/* ── 진단 ─────────────────────────────────────────────────────────────────
   주소에 ?fx=cherry 처럼 붙이면 페이지가 뜨자마자 그 테마를 뿌리고, 좌상단에 상태를 적는다
   (몇 개 만들었는지·동작 줄이기 여부·오버레이 크기). "안 보여요"를 원격에서 가려내기 위한 것. */
function fxReport(themeId, count, reduced) {
  const dbg = document.getElementById('fx-debug');
  if (!dbg) return;
  const box = document.getElementById('fx');
  const r = box.getBoundingClientRect();
  dbg.textContent = `fx: ${themeId} · ${count}개 · 동작줄이기=${reduced ? '켜짐' : '꺼짐'} · 오버레이 ${Math.round(r.width)}×${Math.round(r.height)} · ${new Date().toLocaleTimeString()}`;
  console.info('[fx]', dbg.textContent);
}
window.addEventListener('DOMContentLoaded', () => {
  const want = new URLSearchParams(location.search).get('fx');
  if (!want) return;
  const dbg = document.createElement('div');
  dbg.id = 'fx-debug'; dbg.className = 'fx-debug'; dbg.textContent = 'fx: 준비 중…';
  document.body.appendChild(dbg);
  setTimeout(() => sprinkle(want in PARTICLES ? want : 'cherry'), 800);
});
