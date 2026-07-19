"use client";
import { useMemo, useState } from "react";
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

  // Chaque optimisation AJOUTE ses tournées en base sans purger les
  // précédentes : afficher tout superpose plusieurs plans et rend la carte
  // illisible. Par défaut on ne montre que les plus récentes (id décroissant).
  const [nbAffichees, setNbAffichees] = useState<number>(8);
  const visibles = useMemo(() => {
    const liste = [...(tournees || [])].sort((a: any, b: any) => (b.id ?? 0) - (a.id ?? 0));
    return nbAffichees > 0 ? liste.slice(0, nbAffichees) : liste;
  }, [tournees, nbAffichees]);

  return (
    <AppShell>
      <PageHeader title="Carte interactive" subtitle="Tournées, dépôt, clients et machines — OpenStreetMap" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", gap: 14 }}>
        <Card style={{ padding: 8 }}>
          <MapView tournees={visibles} missions={missions || []} depot={depot} height={480} />
        </Card>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Affichage</div>
            <select
              value={nbAffichees}
              onChange={(e) => setNbAffichees(Number(e.target.value))}
              style={{ width: "100%", padding: "7px 10px", background: C.navyMid, border: `1px solid ${C.border}`, borderRadius: 7, color: C.text, fontSize: 12, outline: "none" }}
            >
              <option value={5}>5 dernières tournées</option>
              <option value={8}>8 dernières tournées</option>
              <option value={12}>12 dernières tournées</option>
              <option value={0}>Tout l'historique</option>
            </select>
            <div style={{ fontSize: 10, color: C.textDim, marginTop: 6 }}>
              {visibles.length} affichée(s) sur {(tournees || []).length} en base
            </div>
          </Card>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Légende</div>
            {[["🟠", "Dépôt agence"], ["🔵", "Livraison"], ["🟧", "Récupération"]].map(([i, l]) => (
              <div key={l} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 7, fontSize: 12, color: C.textMid }}>
                <span>{i}</span>{l}
              </div>
            ))}
          </Card>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Tournées affichées</div>
            {visibles.map((t: any) => (
              <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
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
