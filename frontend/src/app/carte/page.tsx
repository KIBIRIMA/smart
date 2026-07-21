"use client";
import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Skeleton } from "@/components/ui";
import { useTournees, useMissions, useAgences } from "@/hooks/useApi";
import { C } from "@/lib/theme";

const MapView = dynamic(() => import("@/components/MapView"), {
  ssr: false,
  loading: () => <Skeleton h={480} />,
});

export default function CartePage() {
  const { data: tournees } = useTournees();
  const { data: missions } = useMissions();
  const { data: agences } = useAgences();
  const depot = agences?.[0] ?? null;

  // Sélecteur : "all" = toutes les tournées, sinon l'id d'une seule.
  const [selected, setSelected] = useState<number | "all">("all");

  const liste = useMemo(
    () => [...(tournees || [])].sort((a: any, b: any) => (b.id ?? 0) - (a.id ?? 0)),
    [tournees]
  );

  return (
    <AppShell>
      <PageHeader title="Carte interactive" subtitle="Tournées, dépôt, clients et machines — OpenStreetMap" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", gap: 14 }}>
        <Card style={{ padding: 8 }}>
          <MapView tournees={liste} missions={missions || []} depot={depot} height={520} selectedId={selected} />
        </Card>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Afficher</div>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value === "all" ? "all" : Number(e.target.value))}
              style={{ width: "100%", padding: "7px 10px", background: C.navyMid, border: `1px solid ${C.border}`, borderRadius: 7, color: C.text, fontSize: 12, outline: "none" }}
            >
              <option value="all">Toutes les tournées</option>
              {liste.map((t: any) => (
                <option key={t.id} value={t.id}>
                  {t.chauffeur_nom || `Tournée ${t.id}`} · {t.km} km
                </option>
              ))}
            </select>
            <div style={{ fontSize: 10, color: C.textDim, marginTop: 6 }}>
              {selected === "all"
                ? "Survolez une tournée pour l'isoler ; sélectionnez-en une pour voir l'ordre des arrêts."
                : "Numéros = ordre de passage · flèches = sens de circulation."}
            </div>
          </Card>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Légende</div>
            {[["🟠", "Dépôt agence"], ["🔵", "Livraison"], ["🟣", "Récupération"]].map(([i, l]) => (
              <div key={l} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 7, fontSize: 12, color: C.textMid }}>
                <span>{i}</span>{l}
              </div>
            ))}
          </Card>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Tournées</div>
            {liste.map((t: any) => (
              <div key={t.id}
                onClick={() => setSelected(selected === t.id ? "all" : t.id)}
                style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, cursor: "pointer",
                  padding: "3px 5px", borderRadius: 6, background: selected === t.id ? C.navyMid : "transparent" }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: t.couleur }} />
                <span style={{ fontSize: 11, color: C.textMid }}>{t.chauffeur_nom || "Non assigné"} · {t.km} km</span>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
