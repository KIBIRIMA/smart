"use client";
import { C, ROLE_LABEL } from "@/lib/theme";
import { useAuth } from "@/hooks/useAuth";

export default function Navbar() {
  const { user, logout } = useAuth();
  return (
    <header style={{ height: 52, background: "rgba(6,15,30,.92)", backdropFilter: "blur(12px)",
      borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", padding: "0 22px", gap: 14, flexShrink: 0 }}>
      <div style={{ position: "relative", flex: 1, maxWidth: 280 }}>
        <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", fontSize: 13 }}>🔍</span>
        <input placeholder="Rechercher une mission, un client…" style={{
          width: "100%", height: 34, paddingLeft: 32, background: C.navyMid, border: `1px solid ${C.border}`,
          borderRadius: 8, color: C.text, fontSize: 12, outline: "none" }} />
      </div>
      <span style={{ marginLeft: "auto", fontSize: 11, color: C.textDim }}>Agence Paris Sud — Lieusaint</span>
      {user && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{user.full_name}</div>
            <div style={{ fontSize: 10, color: C.orange }}>{ROLE_LABEL[user.role] || user.role}</div>
          </div>
          <div style={{ width: 32, height: 32, borderRadius: "50%", background: `linear-gradient(135deg,${C.orange},${C.orangeD})`,
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#fff" }}>
            {user.full_name.split(" ").map((n) => n[0]).slice(0, 2).join("")}
          </div>
          <button onClick={logout} title="Déconnexion" style={{ background: C.bgHover, border: `1px solid ${C.border}`,
            color: C.textMid, borderRadius: 7, width: 32, height: 32, cursor: "pointer", fontSize: 14 }}>⏻</button>
        </div>
      )}
    </header>
  );
}
