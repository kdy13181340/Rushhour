import { Route, matchRoutes } from "./routes";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  routes?: Route[];
}

function formatRouteReply(routes: Route[], query: string): string {
  if (routes.length === 0) {
    return `"${query}"에 맞는 서울 가로수 길을 찾지 못했어요.\n\n다음과 같이 물어봐 보세요:\n• 봄 벚꽃길 추천해줘\n• 여름에 시원한 그늘길\n• 가을 은행나무 단풍길\n• 메타세쿼이아 이국적인 길\n• 사계절 내내 걸을 수 있는 길`;
  }

  const lines: string[] = [];

  if (routes.length === 1) {
    const r = routes[0];
    lines.push(`${r.emoji} **${r.name}** 을(를) 추천드려요!`);
    lines.push(`\n📍 구간: ${r.district} — ${r.roads.join(", ")}`);
    lines.push(`🌿 수종: ${r.treeType} (${r.treeCount.toLocaleString()}그루)`);
    lines.push(`🗓 최적 시기: ${r.seasonLabel}`);
    lines.push(`\n${r.description}`);
    lines.push(`\n지도에 경로를 표시했어요.`);
  } else {
    lines.push(`${routes.length}개의 추천 경로를 찾았어요:\n`);
    routes.forEach((r, i) => {
      lines.push(`**${i + 1}. ${r.emoji} ${r.name}**`);
      lines.push(`   ${r.district} · ${r.roads.join(", ")}`);
      lines.push(`   ${r.treeType} · ${r.seasonLabel}\n`);
    });
    lines.push(`지도에 모든 경로를 표시했어요. 더 자세한 정보를 원하시면 특정 길 이름을 말씀해 주세요.`);
  }

  return lines.join("\n");
}

const greetings = ["안녕", "hello", "hi", "헬로", "시작"];
const helpKeywords = ["도움", "help", "뭐", "어떤", "추천", "뭘", "알려"];

export function processQuery(query: string): { text: string; routes: Route[] } {
  const q = query.trim().toLowerCase();

  if (greetings.some((g) => q.includes(g))) {
    return {
      text: "안녕하세요! 서울 가로수 산책길 안내 시스템입니다 🌿\n\n계절이나 원하는 분위기를 말씀해 주시면 지도에 맞춤 경로를 보여드릴게요.\n\n예시:\n• 벚꽃 봄 산책길 추천해줘\n• 여름에 그늘 많은 시원한 길\n• 가을 은행나무 노란 단풍길\n• 메타세쿼이아 이국적인 길",
      routes: [],
    };
  }

  if (helpKeywords.some((h) => q.includes(h)) && q.length < 15) {
    return {
      text: "이런 가로수 테마 길을 안내해드릴 수 있어요:\n\n🌸 **벚꽃 봄산책** — 금천·관악구\n🌳 **여름 그늘길** — 서초·노원구\n❄️ **이팝 흰꽃길** — 구로·송파구 (5월)\n🟡 **은행 단풍길** — 송파·용산구\n🍂 **은행 냄새 회피** — 강동구\n🌲 **메타세쿼이아길** — 강남구 양재천\n🍁 **단풍 명소길** — 서초·강남구\n🌿 **상록 소나무길** — 중구\n\n원하시는 길을 말씀해 주세요!",
      routes: [],
    };
  }

  const matched = matchRoutes(query);
  return {
    text: formatRouteReply(matched, query),
    routes: matched,
  };
}
