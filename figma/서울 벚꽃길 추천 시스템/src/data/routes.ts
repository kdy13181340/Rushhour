export type Season = "spring" | "summer" | "fall" | "winter" | "allseason";

export interface Route {
  id: string;
  emoji: string;
  name: string;
  nameEn: string;
  treeType: string;
  treeCount: number;
  season: Season;
  seasonLabel: string;
  district: string;
  roads: string[];
  description: string;
  color: string;
  keywords: string[];
  paths: [number, number][][]; // array of polylines [lat, lng]
}

export const routes: Route[] = [
  {
    id: "cherry",
    emoji: "🌸",
    name: "벚꽃 봄산책길",
    nameEn: "Cherry Blossom Spring Walk",
    treeType: "벚나무류",
    treeCount: 31550,
    season: "spring",
    seasonLabel: "봄 (3~4월)",
    district: "금천구·관악구",
    roads: ["벚꽃로", "난곡로"],
    description: "서울에서 벚꽃이 가장 풍성한 구간입니다. 금천 벚꽃로와 관악 난곡로를 따라 31,550그루의 벚나무가 봄을 맞이합니다.",
    color: "#e8a0b0",
    keywords: ["벚꽃", "봄", "spring", "cherry", "벚나무", "꽃길"],
    paths: [
      // 금천 벚꽃로 approximate
      [[37.4583, 126.8946], [37.4621, 126.8978], [37.4658, 126.9010], [37.4695, 126.9042]],
      // 관악 난곡로 approximate
      [[37.4772, 126.9021], [37.4735, 126.9045], [37.4698, 126.9069], [37.4661, 126.9093]],
    ],
  },
  {
    id: "shade",
    emoji: "🌳",
    name: "여름 그늘 시원길",
    nameEn: "Summer Shade Cool Path",
    treeType: "플라타너스·느티나무",
    treeCount: 83806,
    season: "summer",
    seasonLabel: "여름 (6~8월)",
    district: "서초구·노원구",
    roads: ["강남대로", "동일로"],
    description: "플라타너스 43,680그루와 느티나무 40,126그루가 만드는 서울 최고의 여름 그늘길. 강남대로와 노원 동일로가 대표 구간입니다.",
    color: "#2d6a4f",
    keywords: ["그늘", "여름", "summer", "시원", "플라타너스", "느티", "shade"],
    paths: [
      // 서초 강남대로
      [[37.5034, 127.0245], [37.4967, 127.0280], [37.4900, 127.0315], [37.4833, 127.0350]],
      // 노원 동일로
      [[37.6551, 127.0630], [37.6620, 127.0658], [37.6689, 127.0686], [37.6758, 127.0714]],
    ],
  },
  {
    id: "ipaeb",
    emoji: "❄️",
    name: "이팝나무 흰꽃길",
    nameEn: "Ipaeb White Flower Path",
    treeType: "이팝나무",
    treeCount: 26922,
    season: "spring",
    seasonLabel: "늦봄 (5월)",
    district: "구로구·송파구",
    roads: ["서해안로", "동남로"],
    description: "5월이면 이팝나무 26,922그루가 하얀 꽃눈을 내리는 것처럼 피어납니다. 구로 서해안로와 송파 동남로가 명소입니다.",
    color: "#b7e4c7",
    keywords: ["이팝", "흰꽃", "5월", "늦봄", "이팝나무"],
    paths: [
      // 구로 서해안로 approximate
      [[37.4882, 126.8571], [37.4845, 126.8623], [37.4808, 126.8675], [37.4771, 126.8727]],
      // 송파 동남로
      [[37.5012, 127.1089], [37.4975, 127.1145], [37.4938, 127.1201], [37.4901, 127.1257]],
    ],
  },
  {
    id: "ginkgo-avoid",
    emoji: "🍂",
    name: "은행 냄새 회피길",
    nameEn: "Ginkgo Smell Avoidance Route",
    treeType: "은행나무 암나무",
    treeCount: 15316,
    season: "fall",
    seasonLabel: "가을 (10~11월)",
    district: "강동구",
    roads: ["동남로", "올림픽로"],
    description: "강동 동남로와 올림픽로는 가을에 은행 냄새가 심한 구간입니다. 이 길을 우회해 쾌적하게 이동하세요.",
    color: "#f4a261",
    keywords: ["은행", "냄새", "회피", "ginkgo", "강동"],
    paths: [
      // 강동 동남로
      [[37.5283, 127.1195], [37.5246, 127.1250], [37.5209, 127.1305], [37.5172, 127.1360]],
      // 올림픽로 일부
      [[37.5241, 127.0890], [37.5241, 127.1000], [37.5241, 127.1110], [37.5241, 127.1220]],
    ],
  },
  {
    id: "ginkgo-enjoy",
    emoji: "🟡",
    name: "가을 은행 단풍길",
    nameEn: "Fall Ginkgo Foliage Walk",
    treeType: "은행나무",
    treeCount: 99049,
    season: "fall",
    seasonLabel: "가을 (10~11월)",
    district: "송파구·용산구",
    roads: ["위례성대로", "소월로"],
    description: "서울에서 가장 많은 은행나무 99,049그루를 자랑하는 황금빛 단풍길. 송파 위례성대로와 용산 소월로가 압권입니다.",
    color: "#f9c74f",
    keywords: ["은행", "단풍", "가을", "fall", "autumn", "노란", "황금", "용산", "송파"],
    paths: [
      // 송파 위례성대로
      [[37.4882, 127.1340], [37.4921, 127.1380], [37.4960, 127.1420], [37.4999, 127.1460]],
      // 용산 소월로
      [[37.5496, 126.9836], [37.5524, 126.9875], [37.5552, 126.9914], [37.5580, 126.9953]],
    ],
  },
  {
    id: "metasequoia",
    emoji: "🌲",
    name: "메타세쿼이아 이국길",
    nameEn: "Metasequoia Exotic Path",
    treeType: "메타세쿼이아",
    treeCount: 4747,
    season: "allseason",
    seasonLabel: "사계절",
    district: "강남구",
    roads: ["양재천로"],
    description: "강남 양재천로에 732그루가 밀집한 이국적인 메타세쿼이아 터널. 사계절 내내 다른 매력을 선사합니다.",
    color: "#40916c",
    keywords: ["메타세쿼이아", "이국", "터널", "양재천", "강남", "사계절"],
    paths: [
      // 강남 양재천로
      [[37.4813, 127.0410], [37.4776, 127.0448], [37.4739, 127.0486], [37.4702, 127.0524], [37.4665, 127.0562]],
    ],
  },
  {
    id: "maple",
    emoji: "🍁",
    name: "단풍 명소길",
    nameEn: "Autumn Maple Highlight",
    treeType: "중국단풍·대왕참나무·칠엽수",
    treeCount: 6843,
    season: "fall",
    seasonLabel: "가을 (10~11월)",
    district: "서초구·강남구",
    roads: ["신반포로", "밤고개로"],
    description: "중국단풍, 대왕참나무, 칠엽수가 어우러진 서초·강남의 단풍 명소. 신반포로와 밤고개로에서 붉고 주황빛 단풍을 만끽하세요.",
    color: "#e76f51",
    keywords: ["단풍", "가을", "fall", "maple", "붉은", "서초", "강남", "중국단풍"],
    paths: [
      // 서초 신반포로
      [[37.5083, 126.9988], [37.5052, 127.0028], [37.5021, 127.0068], [37.4990, 127.0108]],
      // 강남 밤고개로
      [[37.4950, 127.0680], [37.4983, 127.0718], [37.5016, 127.0756], [37.5049, 127.0794]],
    ],
  },
  {
    id: "evergreen",
    emoji: "🌿",
    name: "사철 푸른 상록길",
    nameEn: "Year-round Evergreen Path",
    treeType: "소나무",
    treeCount: 5216,
    season: "allseason",
    seasonLabel: "사계절",
    district: "중구",
    roads: ["퇴계로", "다산로"],
    description: "중구 퇴계로와 다산로에 자리한 소나무 5,216그루. 겨울에도 푸르름을 잃지 않는 서울 도심의 사계절 녹색 통로입니다.",
    color: "#1b4332",
    keywords: ["소나무", "상록", "사계절", "겨울", "winter", "evergreen", "중구", "퇴계로"],
    paths: [
      // 중구 퇴계로
      [[37.5615, 126.9901], [37.5598, 126.9958], [37.5581, 127.0015], [37.5564, 127.0072]],
      // 다산로
      [[37.5630, 127.0105], [37.5647, 127.0143], [37.5664, 127.0181]],
    ],
  },
];

export function matchRoutes(query: string): Route[] {
  const q = query.toLowerCase();
  const matched = routes.filter((r) =>
    r.keywords.some((k) => q.includes(k.toLowerCase()))
  );
  // season keyword fallback
  if (matched.length === 0) {
    if (q.includes("봄") || q.includes("spring")) return routes.filter(r => r.season === "spring");
    if (q.includes("여름") || q.includes("summer")) return routes.filter(r => r.season === "summer");
    if (q.includes("가을") || q.includes("fall") || q.includes("autumn")) return routes.filter(r => r.season === "fall");
    if (q.includes("겨울") || q.includes("winter")) return routes.filter(r => r.season === "winter" || r.season === "allseason");
    if (q.includes("사계절") || q.includes("allseason")) return routes.filter(r => r.season === "allseason");
  }
  return matched;
}
