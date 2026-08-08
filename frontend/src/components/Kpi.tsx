"use client";
import { C } from "@/lib/theme";
import { Skeleton } from "./ui";
import { Donut } from "./viz";
import type { Kpi as KpiType } from "@/types";

const fmt = (n: number) => n?.toLocaleString("fr-FR") ?? "—";

export default function KpiGrid({ kpi, loading }: { kpi?: KpiType; loading?: boolean }) {
  // Le remplissage est mis en avant comme DONUT (borné 0–100).
  // Les autres KPI restent en gros chiffres marine, valeurs vertueuses en vert.
  const cards = kpi ? [
    { label: "Missions", val: fmt(kpi.missions), unit: "", color: C.brand },
    { label: "Tournées", val: fmt(kpi.tournees), unit: "", color: C.brand },
    { label: "Kilomètres", val: fmt(kpi.km), unit: "km", color: C.brand },
    { label: "Remplissage", val: kpi.taux_remplissage.toFixed(1), unit: "%", color: C.ok, donut: kpi.taux_remplissage },
    { label: "Coût estimé", val: fmt(kpi.cout_estime), unit: "€", color: C.brand },
    { label: "Carburant", val: fmt(kpi.carburant_l), unit: "L", color: C.brand },
    { label: "CO₂", val: fmt(kpi.co2_kg), unit: "kg", color: C.brand },
    { label: "Économies", val: fmt(kpi.economies), unit: "€", color: C.ok },
  ] : [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 16 }}>
      {loading || !kpi
        ? Array.from({ length: 8 }).map((_, i) => (
            <div key={i} style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16, boxShadow: C.shadow }}>
              <Skeleton h={11} w="45%" /><div style={{ height: 10 }} /><Skeleton h={26} w="55%" />
            </div>
          ))
        : cards.map((k) => (
            <div key={k.label} style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: 16, boxShadow: C.shadow, display: "flex", alignItems: "center",
              justifyContent: "space-between", minHeight: 92 }}>
              <div>
                <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: ".05em",
                  textTransform: "uppercase", color: C.textFaint }}>{k.label}</div>
                <div style={{ fontSize: 26, fontWeight: 800, color: k.color, lineHeight: 1, marginTop: 8 }}>
                  {k.val}{k.unit && <span style={{ fontSize: 12, fontWeight: 500, color: C.textMut, marginLeft: 3 }}>{k.unit}</span>}
                </div>
              </div>
              {"donut" in k && k.donut !== undefined && (
                <Donut value={Math.round(k.donut)} size={62} stroke={8} color={C.ok} center={`${Math.round(k.donut)}%`} />
              )}
            </div>
          ))}
    </div>
  );
}
