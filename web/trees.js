/* 수종별 나무 그림 — figma/서울 벚꽃길 추천 시스템/src/components/TreeMarkers.tsx 이식.
   시안의 SVG 생성 함수를 타입만 걷어내고 그대로 옮겼다. 좌표·색·투명도를 바꾸지 않았다.
   키는 api.py PRESENTATION의 slug와 같다(cherry·shade·ipaeb·ginkgo-avoid·
   ginkgo-enjoy·metasequoia·maple·evergreen). */

const TREE_SVGS = {
  cherry: (s, seed) => {
    const petal = (a, r) =>
      `<ellipse cx="${s / 2 + Math.cos(a) * r}" cy="${s * 0.38 + Math.sin(a) * r * 0.7}" rx="${s * 0.11}" ry="${s * 0.09}" fill="#f8b4cc" opacity="0.85" transform="rotate(${a * 57},${s / 2 + Math.cos(a) * r},${s * 0.38 + Math.sin(a) * r * 0.7})"/>`;
    const petals = [0, 1, 2, 3, 4, 5, 6]
      .map((i) => petal((i / 7) * Math.PI * 2 + seed * 0.3, s * 0.22)).join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s + 10}" viewBox="0 0 ${s} ${s + 10}">
      <line x1="${s/2}" y1="${s*0.55}" x2="${s/2}" y2="${s+8}" stroke="#8B5E3C" stroke-width="${s*0.07}" stroke-linecap="round"/>
      <line x1="${s/2}" y1="${s*0.65}" x2="${s*0.3}" y2="${s*0.78}" stroke="#8B5E3C" stroke-width="${s*0.04}" stroke-linecap="round"/>
      <circle cx="${s/2}" cy="${s*0.38}" r="${s*0.32}" fill="#f9d0e0" opacity="0.92"/>
      <circle cx="${s/2-s*0.1}" cy="${s*0.3}" r="${s*0.22}" fill="#f4a8c4" opacity="0.88"/>
      <circle cx="${s/2+s*0.12}" cy="${s*0.28}" r="${s*0.2}" fill="#f9c0d8" opacity="0.85"/>
      ${petals}
      <circle cx="${s/2}" cy="${s*0.38}" r="${s*0.06}" fill="#e87da8"/>
      <circle cx="${s*0.38}" cy="${s*0.3}" r="${s*0.04}" fill="#e87da8"/>
      <circle cx="${s*0.62}" cy="${s*0.32}" r="${s*0.04}" fill="#e87da8"/>
    </svg>`;
  },

  shade: (s) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s+10}" viewBox="0 0 ${s} ${s+10}">
    <line x1="${s/2}" y1="${s*0.6}" x2="${s/2}" y2="${s+8}" stroke="#5c4033" stroke-width="${s*0.09}" stroke-linecap="round"/>
    <line x1="${s/2}" y1="${s*0.72}" x2="${s*0.25}" y2="${s*0.88}" stroke="#5c4033" stroke-width="${s*0.05}" stroke-linecap="round"/>
    <line x1="${s/2}" y1="${s*0.72}" x2="${s*0.75}" y2="${s*0.88}" stroke="#5c4033" stroke-width="${s*0.05}" stroke-linecap="round"/>
    <ellipse cx="${s/2}" cy="${s*0.38}" rx="${s*0.38}" ry="${s*0.3}" fill="#2d6a4f" opacity="0.9"/>
    <ellipse cx="${s*0.35}" cy="${s*0.3}" rx="${s*0.26}" ry="${s*0.22}" fill="#40916c" opacity="0.88"/>
    <ellipse cx="${s*0.65}" cy="${s*0.32}" rx="${s*0.24}" ry="${s*0.2}" fill="#52b788" opacity="0.82"/>
    <ellipse cx="${s/2}" cy="${s*0.22}" rx="${s*0.2}" ry="${s*0.17}" fill="#74c69d" opacity="0.75"/>
  </svg>`,

  ipaeb: (s) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s+10}" viewBox="0 0 ${s} ${s+10}">
    <line x1="${s/2}" y1="${s*0.58}" x2="${s/2}" y2="${s+8}" stroke="#7c5c3e" stroke-width="${s*0.07}" stroke-linecap="round"/>
    <ellipse cx="${s/2}" cy="${s*0.35}" rx="${s*0.33}" ry="${s*0.28}" fill="#d8f3dc" opacity="0.95"/>
    <ellipse cx="${s*0.38}" cy="${s*0.28}" rx="${s*0.23}" ry="${s*0.19}" fill="#eaf7ec" opacity="0.9"/>
    <ellipse cx="${s*0.62}" cy="${s*0.3}" rx="${s*0.21}" ry="${s*0.18}" fill="#f0fbf1" opacity="0.88"/>
    <circle cx="${s/2}" cy="${s*0.2}" r="${s*0.06}" fill="white" stroke="#b7e4c7" stroke-width="1"/>
    <circle cx="${s*0.36}" cy="${s*0.18}" r="${s*0.05}" fill="white" stroke="#b7e4c7" stroke-width="1"/>
    <circle cx="${s*0.64}" cy="${s*0.19}" r="${s*0.045}" fill="white" stroke="#b7e4c7" stroke-width="1"/>
    <circle cx="${s*0.28}" cy="${s*0.35}" r="${s*0.04}" fill="white" stroke="#b7e4c7" stroke-width="1"/>
    <circle cx="${s*0.72}" cy="${s*0.33}" r="${s*0.04}" fill="white" stroke="#b7e4c7" stroke-width="1"/>
    <circle cx="${s*0.5}" cy="${s*0.42}" r="${s*0.04}" fill="white" stroke="#b7e4c7" stroke-width="1"/>
  </svg>`,

  'ginkgo-avoid': (s) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s+10}" viewBox="0 0 ${s} ${s+10}">
    <line x1="${s/2}" y1="${s*0.62}" x2="${s/2}" y2="${s+8}" stroke="#5c4a1e" stroke-width="${s*0.07}" stroke-linecap="round"/>
    <ellipse cx="${s/2}" cy="${s*0.38}" rx="${s*0.28}" ry="${s*0.35}" fill="#f4a261" opacity="0.88"/>
    <ellipse cx="${s*0.38}" cy="${s*0.32}" rx="${s*0.2}" ry="${s*0.25}" fill="#e9803a" opacity="0.82"/>
    <ellipse cx="${s*0.6}" cy="${s*0.3}" rx="${s*0.19}" ry="${s*0.23}" fill="#f9b88a" opacity="0.78"/>
    <path d="M${s/2},${s*0.14} Q${s*0.42},${s*0.2} ${s*0.36},${s*0.28} Q${s*0.44},${s*0.22} ${s/2},${s*0.14}" fill="#fcd5a8" opacity="0.7"/>
    <path d="M${s/2},${s*0.14} Q${s*0.58},${s*0.2} ${s*0.64},${s*0.28} Q${s*0.56},${s*0.22} ${s/2},${s*0.14}" fill="#fcd5a8" opacity="0.7"/>
    <circle cx="${s/2}" cy="${s*0.14}" r="${s*0.03}" fill="#e9803a"/>
  </svg>`,

  'ginkgo-enjoy': (s) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s+10}" viewBox="0 0 ${s} ${s+10}">
    <line x1="${s/2}" y1="${s*0.6}" x2="${s/2}" y2="${s+8}" stroke="#5c4a1e" stroke-width="${s*0.08}" stroke-linecap="round"/>
    <ellipse cx="${s/2}" cy="${s*0.36}" rx="${s*0.3}" ry="${s*0.34}" fill="#f9c74f" opacity="0.93"/>
    <ellipse cx="${s*0.37}" cy="${s*0.28}" rx="${s*0.22}" ry="${s*0.26}" fill="#fdd166" opacity="0.88"/>
    <ellipse cx="${s*0.63}" cy="${s*0.29}" rx="${s*0.2}" ry="${s*0.24}" fill="#ffe08a" opacity="0.82"/>
    ${[0,1,2,3,4].map((i) => {
      const a = (i/5)*Math.PI*2;
      const r = s*0.24;
      const cx = s/2 + Math.cos(a)*r*0.55;
      const cy = s*0.3 + Math.sin(a)*r*0.5;
      return `<path d="M${cx},${cy} Q${cx+Math.cos(a+0.5)*s*0.12},${cy+Math.sin(a+0.5)*s*0.1} ${cx+Math.cos(a)*s*0.18},${cy+Math.sin(a)*s*0.15} Q${cx+Math.cos(a-0.5)*s*0.12},${cy+Math.sin(a-0.5)*s*0.1} ${cx},${cy}" fill="#ffe566" opacity="0.7"/>`;
    }).join('')}
  </svg>`,

  metasequoia: (s) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s*0.7}" height="${s+12}" viewBox="0 0 ${s*0.7} ${s+12}">
    <line x1="${s*0.35}" y1="${s*0.8}" x2="${s*0.35}" y2="${s+10}" stroke="#5c4033" stroke-width="${s*0.07}" stroke-linecap="round"/>
    <polygon points="${s*0.35},${s*0.04} ${s*0.08},${s*0.45} ${s*0.62},${s*0.45}" fill="#1b4332" opacity="0.93"/>
    <polygon points="${s*0.35},${s*0.18} ${s*0.06},${s*0.55} ${s*0.64},${s*0.55}" fill="#2d6a4f" opacity="0.9"/>
    <polygon points="${s*0.35},${s*0.32} ${s*0.04},${s*0.68} ${s*0.66},${s*0.68}" fill="#40916c" opacity="0.87"/>
    <polygon points="${s*0.35},${s*0.45} ${s*0.02},${s*0.82} ${s*0.68},${s*0.82}" fill="#52b788" opacity="0.82"/>
    <line x1="${s*0.35}" y1="${s*0.04}" x2="${s*0.35}" y2="${s*0.82}" stroke="#1b4332" stroke-width="${s*0.04}" opacity="0.5"/>
  </svg>`,

  maple: (s, seed) => {
    const colors = ['#e76f51','#f4a261','#e63946','#d62828','#f8961e'];
    const blobs = [0,1,2,3,4,5].map((i) => {
      const a = (i/6)*Math.PI*2 + seed*0.2;
      const r = s*(0.18+((seed*7+i*3)%5)*0.02);
      const cx = s/2+Math.cos(a)*s*0.18;
      const cy = s*0.36+Math.sin(a)*s*0.15;
      return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${colors[(i+seed)%colors.length]}" opacity="0.82"/>`;
    }).join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s+10}" viewBox="0 0 ${s} ${s+10}">
      <line x1="${s/2}" y1="${s*0.6}" x2="${s/2}" y2="${s+8}" stroke="#6d4c41" stroke-width="${s*0.07}" stroke-linecap="round"/>
      <circle cx="${s/2}" cy="${s*0.36}" r="${s*0.32}" fill="#f4a261" opacity="0.88"/>
      ${blobs}
      <circle cx="${s/2}" cy="${s*0.23}" r="${s*0.18}" fill="#e63946" opacity="0.82"/>
    </svg>`;
  },

  evergreen: (s) => `<svg xmlns="http://www.w3.org/2000/svg" width="${s*0.8}" height="${s+10}" viewBox="0 0 ${s*0.8} ${s+10}">
    <line x1="${s*0.4}" y1="${s*0.75}" x2="${s*0.4}" y2="${s+8}" stroke="#4a3728" stroke-width="${s*0.07}" stroke-linecap="round"/>
    <polygon points="${s*0.4},${s*0.06} ${s*0.1},${s*0.42} ${s*0.7},${s*0.42}" fill="#1b4332" opacity="0.95"/>
    <polygon points="${s*0.4},${s*0.24} ${s*0.08},${s*0.58} ${s*0.72},${s*0.58}" fill="#2d6a4f" opacity="0.9"/>
    <polygon points="${s*0.4},${s*0.42} ${s*0.06},${s*0.76} ${s*0.74},${s*0.76}" fill="#40916c" opacity="0.85"/>
    <line x1="${s*0.4}" y1="${s*0.06}" x2="${s*0.4}" y2="${s*0.76}" stroke="#1b4332" stroke-width="${s*0.035}" opacity="0.4"/>
    <line x1="${s*0.4}" y1="${s*0.35}" x2="${s*0.15}" y2="${s*0.48}" stroke="#1b4332" stroke-width="${s*0.025}" opacity="0.35"/>
    <line x1="${s*0.4}" y1="${s*0.35}" x2="${s*0.65}" y2="${s*0.48}" stroke="#1b4332" stroke-width="${s*0.025}" opacity="0.35"/>
  </svg>`,
};

/* 시안의 크기 변주 — 같은 수종이라도 그루마다 조금씩 다르게 보이게 한다. */
const SIZE_VARIANTS = [38, 42, 36, 44, 40, 38, 46, 34, 40, 42];

/** 나무 한 그루짜리 Leaflet divIcon. 시안과 같이 밑동(anchor)을 좌표에 맞춘다. */
function treeIcon(routeId, seed) {
  const size = SIZE_VARIANTS[seed % SIZE_VARIANTS.length];
  const draw = TREE_SVGS[routeId] || TREE_SVGS.shade;
  const w = (routeId === 'metasequoia' || routeId === 'evergreen') ? size * 0.7 : size;
  const h = size + 12;
  return L.divIcon({
    html: draw(size, seed), className: 'tree-pin',
    iconSize: [w, h], iconAnchor: [w / 2, h],
  });
}
