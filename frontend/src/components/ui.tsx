"use client";
import { C } from "@/lib/theme";
import type { ReactNode } from "react";

export const Card = ({ children, style }: { children: ReactNode; style?: React.CSSProperties }) => (
  <div style={{ background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 10, padding: 16, ...style }}>
    {children}
  </div>
);

export const Chip = ({ label, color = C.textDim }: { label: string; color?: string }) => (
  <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 9px", borderRadius: 12,
    fontSize: 11, fontWeight: 600, background: `${color}22`, color, border: `1px solid ${color}40` }}>
    {label}
  </span>
);

const STATUT: Record<string, string> = {
  A_PLANIFIER: C.textDim, PLANIFIEE: "#93C5FD", EN_COURS: C.yellow, EN_ROUTE: C.green, TERMINEE: C.green,
};
const STATUT_L: Record<string, string> = {
  A_PLANIFIER: "À planifier", PLANIFIEE: "Planifiée", EN_COURS: "En cours", EN_ROUTE: "En route", TERMINEE: "Terminée",
};
export const StatusChip = ({ s }: { s: string }) => <Chip label={STATUT_L[s] || s} color={STATUT[s] || C.textDim} />;
export const TypeChip = ({ t }: { t: string }) =>
  <Chip label={t === "livraison" ? "Livraison" : "Récup."} color={t === "livraison" ? C.cyan : C.orange} />;

export const Bar = ({ pct }: { pct: number }) => {
  const col = pct > 85 ? C.green : pct > 60 ? C.orange : C.yellow;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ flex: 1, height: 5, background: C.navyLt, borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: col, borderRadius: 3, transition: "width .8s" }} />
      </div>
      <span style={{ fontSize: 10, fontWeight: 700, color: col, width: 30, textAlign: "right" }}>{Math.round(pct)}%</span>
    </div>
  );
};

export const Spinner = ({ size = 18 }: { size?: number }) => (
  <div style={{ width: size, height: size, border: `2px solid ${C.border}`, borderTopColor: C.orange,
    borderRadius: "50%", animation: "spin .8s linear infinite" }} />
);

export const Skeleton = ({ h = 16, w = "100%" }: { h?: number; w?: number | string }) => (
  <div style={{ height: h, width: w, background: `linear-gradient(90deg,${C.navyMid},${C.bgHover},${C.navyMid})`,
    backgroundSize: "200% 100%", borderRadius: 6, animation: "shimmer 1.4s infinite" }} />
);

export const EmptyState = ({ icon = "📭", title, hint }: { icon?: string; title: string; hint?: string }) => (
  <div style={{ textAlign: "center", padding: "40px 20px", color: C.textMid }}>
    <div style={{ fontSize: 32, marginBottom: 10 }}>{icon}</div>
    <div style={{ fontWeight: 600, fontSize: 14 }}>{title}</div>
    {hint && <div style={{ fontSize: 12, color: C.textDim, marginTop: 4 }}>{hint}</div>}
  </div>
);
