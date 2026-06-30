"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { C } from "@/lib/theme";

const NAV = [
  { href: "/dashboard", icon: "🏠", label: "Tableau de bord" },
  { href: "/optimisation", icon: "⚡", label: "Optimisation" },
  { href: "/simulation", icon: "🔮", label: "Simulation" },
  { href: "/missions", icon: "📋", label: "Missions" },
  { href: "/tournees", icon: "🚛", label: "Tournées" },
  { href: "/carte", icon: "🗺️", label: "Carte" },
  { href: "/machines", icon: "🏗️", label: "Machines" },
  { href: "/vehicules", icon: "🚚", label: "Véhicules" },
  { href: "/chauffeurs", icon: "👥", label: "Chauffeurs" },
  { href: "/clients", icon: "🏢", label: "Clients" },
  { href: "/parametres", icon: "⚙️", label: "Paramètres" },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside style={{ width: 210, background: C.navy, borderRight: `1px solid ${C.border}`,
      display: "flex", flexDirection: "column", flexShrink: 0, height: "100vh" }}>
      <div style={{ padding: "16px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 9 }}>
        <div style={{ width: 34, height: 34, background: `linear-gradient(135deg,${C.orange},${C.orangeD})`,
          borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: `0 0 16px ${C.orange}40` }}>🚛</div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 800, color: C.text, lineHeight: 1.2 }}>Smart Transport AI</div>
          <div style={{ fontSize: 9, color: C.orange, fontWeight: 700, letterSpacing: ".06em" }}>ACCÈS INDUSTRIE</div>
        </div>
      </div>
      <div style={{ margin: "9px 10px", display: "flex", alignItems: "center", gap: 6, padding: "6px 9px",
        background: `${C.green}10`, borderRadius: 7, border: `1px solid ${C.green}25` }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: C.green, animation: "pulse 2s infinite" }} />
        <span style={{ fontSize: 10, color: C.green, fontWeight: 600 }}>Moteur v12 connecté</span>
      </div>
      <nav style={{ flex: 1, padding: "6px 8px", overflowY: "auto" }}>
        {NAV.map((it) => {
          const active = path === it.href || path.startsWith(it.href + "/");
          return (
            <Link key={it.href} href={it.href} style={{
              display: "flex", alignItems: "center", gap: 9, padding: "9px 11px", borderRadius: 8,
              marginBottom: 2, textDecoration: "none", fontSize: 12,
              background: active ? `${C.orange}18` : "transparent",
              border: `1px solid ${active ? C.orange + "45" : "transparent"}`,
              color: active ? C.orange : C.textMid, fontWeight: active ? 700 : 400,
            }}>
              <span style={{ fontSize: 14 }}>{it.icon}</span>{it.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
