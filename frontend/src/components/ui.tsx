"use client";
import { C } from "@/lib/theme";
import type { ReactNode } from "react";

// Reskin clair — signatures identiques à l'original, logique inchangée.
// Seuls les styles internes évoluent (ombres douces, coins arrondis, fond clair).

export const Card = ({ children, style }: { children: ReactNode; style?: React.CSSProperties }) => (
  <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
    padding: 16, boxShadow: C.shadow, ...style }}>
    {children}
  </div>
);

export const Chip = ({ label, color = C.textDim }: { label: string; color?: string }) => (
  <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 9px", borderRadius: 999,
    fontSize: 11, fontWeight: 600, background: `${color}18`, color, border: `1px solid ${color}33` }}>
    {label}
  </span>
);

const STATUT: Record<string, string> = {
  A_PLANIFIER: C.textDim, PLANIFIEE: C.accent, EN_COURS: C.warn, EN_ROUTE: C.green, TERMINEE: C.green,
};
const STATUT_L: Record<string, string> = {
  A_PLANIFIER: "À planifier", PLANIFIEE: "Planifiée", EN_COURS: "En cours", EN_ROUTE: "En route", TERMINEE: "Terminée",
};
export const StatusChip = ({ s }: { s: string }) => <Chip label={STATUT_L[s] || s} color={STATUT[s] || C.textDim} />;

// NOTE convention : le plateau 2.5D utilise livraison = ORANGE, récup = VIOLET.
// L'original mettait ici livraison = cyan / récup = orange (incohérent avec le plateau).
// Aligné sur le plateau pour une convention unique dans toute l'app.
export const TypeChip = ({ t }: { t: string }) =>
  <Chip label={t === "livraison" ? "Livraison" : "Récup."} color={t === "livraison" ? C.livraison : C.recuperation} />;

export const Bar = ({ pct }: { pct: number }) => {
  const col = pct > 85 ? C.green : pct > 60 ? C.warn : C.red;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ flex: 1, height: 6, background: C.track, borderRadius: 999, overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: col, borderRadius: 999, transition: "width .8s" }} />
      </div>
      <span style={{ fontSize: 10, fontWeight: 700, color: col, width: 30, textAlign: "right" }}>{Math.round(pct)}%</span>
    </div>
  );
};

export const Spinner = ({ size = 18 }: { size?: number }) => (
  <div style={{ width: size, height: size, border: `2px solid ${C.border}`, borderTopColor: C.brand,
    borderRadius: "50%", animation: "spin .8s linear infinite" }} />
);

export const Skeleton = ({ h = 16, w = "100%" }: { h?: number; w?: number | string }) => (
  <div style={{ height: h, width: w, background: `linear-gradient(90deg,${C.bgSubtle},${C.bgHover},${C.bgSubtle})`,
    backgroundSize: "200% 100%", borderRadius: 6, animation: "shimmer 1.4s infinite" }} />
);

export const EmptyState = ({ icon = "📭", title, hint }: { icon?: string; title: string; hint?: string }) => (
  <div style={{ textAlign: "center", padding: "40px 20px", color: C.textMid }}>
    <div style={{ fontSize: 32, marginBottom: 10 }}>{icon}</div>
    <div style={{ fontWeight: 600, fontSize: 14, color: C.text }}>{title}</div>
    {hint && <div style={{ fontSize: 12, color: C.textDim, marginTop: 4 }}>{hint}</div>}
  </div>
);
