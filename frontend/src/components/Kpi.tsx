"use client";
import { C } from "@/lib/theme";
import { Skeleton } from "./ui";
import type { Kpi as KpiType } from "@/types";

const fmt = (n: number) => n?.toLocaleString("fr-FR") ?? "—";

export default function KpiGrid({ kpi, loading }: { kpi?: KpiType; loading?: boolean }) {
  const cards = kpi ? [
    { icon: "📋", label: "Missions", val: fmt(kpi.missions), unit: "", color: C.orange },
    { icon: "🚛", label: "Tournées", val: fmt(kpi.tournees), unit: "", color: C.purple },
    { icon: "🛣️", label: "Kilomètres", val: fmt(kpi.km), unit: "km", color: C.green },
    { icon: "📊", label: "Remplissage", val: kpi.taux_remplissage.toFixed(1), unit: "%", color: C.yellow },
    { icon: "💰", label: "Coût estimé", val: fmt(kpi.cout_estime), unit: "€", color: C.cyan },
    { icon: "⛽", label: "Carburant", val: fmt(kpi.carburant_l), unit: "L", color: C.orangeL },
    { icon: "🌿", label: "CO₂", val: fmt(kpi.co2_kg), unit: "kg", color: C.green },
    { icon: "📈", label: "Économies", val: fmt(kpi.economies), unit: "€", color: C.orange },
  ] : [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 16 }}>
      {loading || !kpi
        ? Array.from({ length: 8 }).map((_, i) => (
            <div key={i} style={{ background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
              <Skeleton h={18} w={28} /><div style={{ height: 8 }} /><Skeleton h={24} w="60%" /><div style={{ height: 6 }} /><Skeleton h={11} w="45%" />
            </div>
          ))
        : cards.map((k) => (
            <div key={k.label} style={{ background: C.bgCard, border: `1px solid ${k.color}30`, borderRadius: 10, padding: 14, position: "relative", overflow: "hidden" }}>
              <div style={{ position: "absolute", top: 0, right: 0, width: 50, height: 50, background: `radial-gradient(circle,${k.color}20,transparent)` }} />
              <div style={{ fontSize: 18, marginBottom: 8 }}>{k.icon}</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: k.color, lineHeight: 1 }}>
                {k.val}{k.unit && <span style={{ fontSize: 11, fontWeight: 400, color: C.textMid, marginLeft: 3 }}>{k.unit}</span>}
              </div>
              <div style={{ fontSize: 10, color: C.textMid, marginTop: 3 }}>{k.label}</div>
            </div>
          ))}
    </div>
  );
}
