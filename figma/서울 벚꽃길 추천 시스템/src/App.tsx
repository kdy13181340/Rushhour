import { useState, useRef, useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Polyline,
  useMap,
  Tooltip,
} from "react-leaflet";
import TreeMarkers from "./components/TreeMarkers";
import { LatLngBounds } from "leaflet";
import { routes, Route } from "./data/routes";
import { ChatMessage, processQuery } from "./data/chatbot";

import L from "leaflet";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const SEASON_BG: Record<string, string> = {
  spring:    "linear-gradient(160deg,#fce4ec 0%,#fdf6fa 60%,#e8f5e9 100%)",
  summer:    "linear-gradient(160deg,#e8f5e9 0%,#f1f8f4 60%,#e3f2fd 100%)",
  fall:      "linear-gradient(160deg,#fff8e1 0%,#fffdf5 60%,#fbe9e7 100%)",
  winter:    "linear-gradient(160deg,#e3f2fd 0%,#f5f8ff 60%,#ede7f6 100%)",
  allseason: "linear-gradient(160deg,#f5f3ef 0%,#fafaf8 60%,#eef5ef 100%)",
};

const SEASON_TAG: Record<string, { label: string; color: string }> = {
  spring:    { label: "봄", color: "#e91e8c" },
  summer:    { label: "여름", color: "#2d6a4f" },
  fall:      { label: "가을", color: "#e76900" },
  winter:    { label: "겨울", color: "#1565c0" },
  allseason: { label: "사계절", color: "#546e7a" },
};

const QUICK_CHIPS = [
  { label: "🌸 벚꽃 봄산책", q: "벚꽃길 추천해줘" },
  { label: "🌳 여름 그늘길", q: "여름 그늘 시원한 길" },
  { label: "🟡 가을 은행 단풍", q: "가을 은행 단풍길" },
  { label: "❄️ 이팝 흰꽃길", q: "이팝나무 흰꽃길" },
  { label: "🌲 메타세쿼이아", q: "메타세쿼이아 이국길" },
  { label: "🍁 단풍 명소", q: "단풍 명소길 추천" },
  { label: "🌿 상록 소나무", q: "사철 상록 소나무길" },
  { label: "🍂 은행 냄새 회피", q: "은행 냄새 회피 경로" },
];

function MapFlyTo({ activeRoutes }: { activeRoutes: Route[] }) {
  const map = useMap();
  useEffect(() => {
    if (activeRoutes.length === 0) return;
    const allPoints = activeRoutes.flatMap((r) => r.paths.flat());
    if (allPoints.length === 0) return;
    const bounds = new LatLngBounds(allPoints as [number, number][]);
    map.flyToBounds(bounds, { padding: [80, 80], duration: 1.4, maxZoom: 15 });
  }, [activeRoutes, map]);
  return null;
}

function parseBold(text: string) {
  return text.split(/(\*\*.*?\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i} style={{ fontWeight: 600 }}>{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>
  );
}

function formatMessage(text: string) {
  return text.split("\n").map((line, i, arr) => (
    <span key={i}>{parseBold(line)}{i < arr.length - 1 && <br />}</span>
  ));
}

export default function App() {
  const [activeRoutes, setActiveRoutes] = useState<Route[]>([]);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "안녕하세요! 🌿 **서울 가로수 산책길 안내 시스템**입니다.\n\n계절이나 원하는 분위기를 입력하시면 지도에 경로를 표시해드립니다.\n\n• 봄 벚꽃길 추천해줘\n• 여름에 그늘 많고 시원한 길\n• 가을 은행나무 단풍길\n• 메타세쿼이아 이국적인 터널길",
      routes: [],
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const currentSeason = activeRoutes.length > 0 ? activeRoutes[0].season : "allseason";
  const panelBg = SEASON_BG[currentSeason] || SEASON_BG.allseason;

  function sendQuery(q: string) {
    const userMsg: ChatMessage = { id: Date.now() + "u", role: "user", text: q };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setIsTyping(true);
    setTimeout(() => {
      const result = processQuery(q);
      setMessages((m) => [
        ...m,
        { id: Date.now() + "a", role: "assistant", text: result.text, routes: result.routes },
      ]);
      setActiveRoutes(result.routes);
      setIsTyping(false);
    }, 650);
  }

  function handleSend() {
    const q = input.trim();
    if (q) sendQuery(q);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100vw", overflow: "hidden", background: "#f5f3ef", fontFamily: "'Noto Sans KR', sans-serif" }}>

      {/* ── TOP HEADER ── */}
      <header style={{
        height: 56,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 28px",
        background: "#1a2e22",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        zIndex: 1000,
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: "#52b788", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15 }}>🌿</div>
          <span style={{ color: "#ffffff", fontWeight: 600, fontSize: 15, letterSpacing: "-0.2px" }}>서울 가로수길</span>
          <span style={{ color: "#52b788", fontSize: 12, marginLeft: 2 }}>WALK SEOUL</span>
        </div>

        {/* Season tabs */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {(["spring", "summer", "fall", "allseason"] as const).map((s) => {
            const tag = SEASON_TAG[s];
            const active = currentSeason === s;
            return (
              <div key={s} style={{
                padding: "4px 14px",
                borderRadius: 20,
                fontSize: 12,
                fontWeight: active ? 600 : 400,
                background: active ? tag.color : "rgba(255,255,255,0.08)",
                color: active ? "#fff" : "rgba(255,255,255,0.5)",
                cursor: "default",
                transition: "all 0.3s",
              }}>{tag.label}</div>
            );
          })}
        </div>

        {/* Stats */}
        <div style={{ display: "flex", gap: 20 }}>
          {[
            { label: "테마 경로", value: "8" },
            { label: "가로수 총계", value: "219,447" },
            { label: "커버 구", value: "25" },
          ].map((s) => (
            <div key={s.label} style={{ textAlign: "center" }}>
              <div style={{ color: "#52b788", fontWeight: 700, fontSize: 14 }}>{s.value}</div>
              <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 11 }}>{s.label}</div>
            </div>
          ))}
        </div>
      </header>

      {/* ── MAIN BODY ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* ── LEFT SIDEBAR: Route List ── */}
        <aside style={{
          width: 260,
          flexShrink: 0,
          background: "#ffffff",
          borderRight: "1px solid #e8e5df",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}>
          <div style={{ padding: "16px 16px 10px", borderBottom: "1px solid #f0ede8" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#7a7770", letterSpacing: "0.08em", textTransform: "uppercase" }}>테마 경로 목록</div>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
            {routes.map((route) => {
              const isActive = activeRoutes.some((r) => r.id === route.id);
              const tag = SEASON_TAG[route.season] || SEASON_TAG.allseason;
              return (
                <button
                  key={route.id}
                  onClick={() => sendQuery(route.name + " 추천해줘")}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "10px 12px",
                    borderRadius: 10,
                    border: isActive ? `1.5px solid ${route.color}` : "1.5px solid transparent",
                    background: isActive ? route.color + "12" : "transparent",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                    marginBottom: 2,
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "#f5f3ef"; }}
                  onMouseLeave={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <span style={{ fontSize: 20, lineHeight: 1, flexShrink: 0, marginTop: 1 }}>{route.emoji}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: isActive ? 600 : 500, color: "#1a1a18", lineHeight: 1.3 }}>{route.name}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 4 }}>
                      <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 10, background: tag.color + "18", color: tag.color, fontWeight: 500 }}>{tag.label}</span>
                      <span style={{ fontSize: 10, color: "#9a9690" }}>{route.district}</span>
                    </div>
                  </div>
                  {isActive && (
                    <div style={{ marginLeft: "auto", width: 8, height: 8, borderRadius: "50%", background: route.color, flexShrink: 0, marginTop: 5 }} />
                  )}
                </button>
              );
            })}
          </div>
        </aside>

        {/* ── CENTER: MAP ── */}
        <div style={{ position: "relative", flex: 1, minWidth: 0 }}>
          <MapContainer
            center={[37.5326, 127.024]}
            zoom={12}
            style={{ height: "100%", width: "100%" }}
            zoomControl={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com">CARTO</a>'
              url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            />
            <MapFlyTo activeRoutes={activeRoutes} />
            <TreeMarkers activeRoutes={activeRoutes} />

            {routes.map((route) => {
              const isActive = activeRoutes.some((r) => r.id === route.id);
              const isHovered = hoverId === route.id;
              return route.paths.map((path, pi) => (
                <Polyline
                  key={route.id + "-" + pi}
                  positions={path as [number, number][]}
                  pathOptions={{
                    color: isActive ? route.color : "#c0bdb7",
                    weight: isActive ? (isHovered ? 7 : 5) : 2,
                    opacity: isActive ? 0.55 : 0.25,
                    lineCap: "round",
                    lineJoin: "round",
                    dashArray: isActive ? undefined : "4 6",
                  }}
                  eventHandlers={{
                    mouseover: () => setHoverId(route.id),
                    mouseout: () => setHoverId(null),
                    click: () => sendQuery(route.name + " 추천해줘"),
                  }}
                >
                  {isActive && (
                    <Tooltip sticky className="route-tooltip" offset={[0, -10]}>
                      {route.emoji} {route.name} — {route.roads.join(", ")}
                    </Tooltip>
                  )}
                </Polyline>
              ));
            })}
          </MapContainer>

          {/* Map zoom controls (custom) */}
          <div style={{
            position: "absolute", top: 16, right: 16, zIndex: 1000,
            display: "flex", flexDirection: "column", gap: 4,
          }}>
            {/* placeholder for zoom — leaflet's default is hidden */}
          </div>

          {/* Active route legend */}
          {activeRoutes.length > 0 && (
            <div style={{
              position: "absolute", bottom: 24, left: 16, zIndex: 1000,
              background: "rgba(255,255,255,0.95)",
              backdropFilter: "blur(10px)",
              borderRadius: 14,
              padding: "14px 16px",
              boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
              border: "1px solid rgba(0,0,0,0.07)",
              minWidth: 200,
            }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#7a7770", letterSpacing: "0.06em", marginBottom: 8, textTransform: "uppercase" }}>
                표시된 경로 ({activeRoutes.length})
              </div>
              {activeRoutes.map((r) => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <div style={{ width: 28, height: 4, borderRadius: 2, background: r.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: "#1a1a18", fontWeight: 500 }}>{r.emoji} {r.name}</span>
                </div>
              ))}
            </div>
          )}

          {/* Attribution */}
          <div style={{
            position: "absolute", bottom: 8, right: 8, zIndex: 1000,
            fontSize: 10, color: "#9a9690", background: "rgba(255,255,255,0.8)", borderRadius: 4, padding: "2px 6px",
          }}>
            서울시 가로수 데이터 기반 · OpenStreetMap
          </div>
        </div>

        {/* ── RIGHT: CHAT PANEL ── */}
        <aside style={{
          width: 420,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          background: panelBg,
          transition: "background 0.9s ease",
          borderLeft: "1px solid rgba(0,0,0,0.08)",
        }}>

          {/* Chat header */}
          <div style={{
            padding: "18px 24px 14px",
            flexShrink: 0,
            background: "rgba(255,255,255,0.65)",
            backdropFilter: "blur(14px)",
            borderBottom: "1px solid rgba(0,0,0,0.07)",
          }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#1a1a18", marginBottom: 2 }}>
              🗺 경로 추천 챗봇
            </div>
            <div style={{ fontSize: 12, color: "#7a7770" }}>계절·수종·분위기를 자유롭게 입력하세요</div>

            {/* Quick chips */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
              {QUICK_CHIPS.map((chip) => (
                <button
                  key={chip.q}
                  onClick={() => sendQuery(chip.q)}
                  style={{
                    fontSize: 12,
                    padding: "5px 12px",
                    borderRadius: 20,
                    border: "1px solid rgba(0,0,0,0.1)",
                    background: "rgba(255,255,255,0.8)",
                    color: "#2d6a4f",
                    cursor: "pointer",
                    fontWeight: 500,
                    fontFamily: "'Noto Sans KR', sans-serif",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,1)"; (e.currentTarget as HTMLElement).style.boxShadow = "0 2px 8px rgba(0,0,0,0.1)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.8)"; (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>

          {/* Messages */}
          <div className="chat-scroll" style={{ flex: 1, overflowY: "auto", padding: "20px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
            {messages.map((msg) => (
              <div key={msg.id} style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", alignItems: "flex-start", gap: 10 }}>
                {msg.role === "assistant" && (
                  <div style={{ width: 32, height: 32, borderRadius: 10, background: "rgba(255,255,255,0.85)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0, boxShadow: "0 1px 4px rgba(0,0,0,0.08)" }}>🌿</div>
                )}
                <div style={{
                  maxWidth: "78%",
                  padding: "12px 16px",
                  borderRadius: msg.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
                  fontSize: 14,
                  lineHeight: 1.65,
                  ...(msg.role === "user"
                    ? { background: "#1a2e22", color: "#ffffff" }
                    : { background: "rgba(255,255,255,0.85)", color: "#1a1a18", backdropFilter: "blur(8px)", boxShadow: "0 2px 10px rgba(0,0,0,0.07)" }
                  ),
                }}>
                  {formatMessage(msg.text)}

                  {msg.routes && msg.routes.length > 0 && (
                    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 7 }}>
                      {msg.routes.map((r) => (
                        <button
                          key={r.id}
                          onClick={() => sendQuery(r.name + " 더 자세히 알려줘")}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            width: "100%",
                            textAlign: "left",
                            padding: "10px 12px",
                            borderRadius: 12,
                            border: `1.5px solid ${r.color}44`,
                            background: r.color + "15",
                            cursor: "pointer",
                            fontFamily: "'Noto Sans KR', sans-serif",
                            transition: "all 0.15s",
                          }}
                          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = r.color + "28"; }}
                          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = r.color + "15"; }}
                        >
                          <span style={{ fontSize: 20 }}>{r.emoji}</span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: "#1a1a18" }}>{r.name}</div>
                            <div style={{ fontSize: 11, color: "#7a7770", marginTop: 1 }}>{r.district} · {r.seasonLabel} · {r.treeCount.toLocaleString()}그루</div>
                          </div>
                          <div style={{ width: 10, height: 10, borderRadius: "50%", background: r.color, flexShrink: 0 }} />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isTyping && (
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 32, height: 32, borderRadius: 10, background: "rgba(255,255,255,0.85)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0 }}>🌿</div>
                <div style={{ padding: "12px 16px", borderRadius: "18px 18px 18px 4px", background: "rgba(255,255,255,0.85)", display: "flex", gap: 5, alignItems: "center" }}>
                  {[0, 1, 2].map((i) => (
                    <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: "#7a7770", animation: `dotBounce 1.2s ease-in-out ${i * 0.2}s infinite` }} />
                  ))}
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input area */}
          <div style={{
            flexShrink: 0,
            padding: "16px 20px 20px",
            background: "rgba(255,255,255,0.65)",
            backdropFilter: "blur(14px)",
            borderTop: "1px solid rgba(0,0,0,0.07)",
          }}>
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              background: "rgba(255,255,255,0.95)",
              border: "1.5px solid rgba(0,0,0,0.1)",
              borderRadius: 14,
              padding: "10px 14px",
              boxShadow: "0 2px 16px rgba(0,0,0,0.07)",
              transition: "border-color 0.2s",
            }}
              onFocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "#52b788"; }}
              onBlur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.1)"; }}
            >
              <input
                style={{
                  flex: 1,
                  fontSize: 14,
                  outline: "none",
                  background: "transparent",
                  color: "#1a1a18",
                  fontFamily: "'Noto Sans KR', sans-serif",
                  border: "none",
                }}
                placeholder="예: 가을에 은행나무 단풍길 추천해줘"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  border: "none",
                  background: input.trim() ? "#1a2e22" : "#e8e5df",
                  color: input.trim() ? "#ffffff" : "#9a9690",
                  cursor: input.trim() ? "pointer" : "default",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  transition: "all 0.15s",
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
            <div style={{ fontSize: 11, color: "#9a9690", textAlign: "center", marginTop: 8 }}>
              서울시 가로수 공개데이터 기반 · 실제 경로와 차이가 있을 수 있습니다
            </div>
          </div>
        </aside>
      </div>

      <style>{`
        @keyframes dotBounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-6px); }
        }
      `}</style>
    </div>
  );
}
