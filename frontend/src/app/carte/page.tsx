"use client";
import dynamic from "next/dynamic";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Skeleton } from "@/components/ui";
import { useTournees, useMissions, useAgences } from "@/hooks/useApi";
import { C } from "@/lib/theme";

// Leaflet ne fonctionne pas en SSR → import dynamique sans SSR
const MapView = dynamic(() => import("@/components/MapView"), {
  ssr: false,
  loading: () => <Skeleton h={480} />,
});

export default function CartePage() {
  const { data: tournees } = useTournees();
  const { data: missions } = useMissions();
  const { data: agences } = useAgences();
  const depot = agences?.[0] ?? null;

  return (
    <AppShell>
      <PageHeader title="Carte interactive" subtitle="Tournées, dépôt, clients et machines — OpenStreetMap" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", gap: 14 }}>
        <Card style={{ padding: 8 }}>
          <MapView tournees={tournees || []} missions={missions || []} depot={depot} height={480} />
        </Card>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Légende</div>
            {[["🟠", "Dépôt agence"], ["🔵", "Livraison"], ["🟧", "Récupération"]].map(([i, l]) => (
              <div key={l} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 7, fontSize: 12, color: C.textMid }}>
                <span>{i}</span>{l}
              </div>
            ))}
          </Card>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Tournées</div>
            {(tournees || []).map((t) => (
              <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: t.couleur }} />
                <span style={{ fontSize: 11, color: C.textMid }}>{t.chauffeur_nom} · {t.km} km</span>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
