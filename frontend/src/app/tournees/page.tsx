"use client";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, StatusChip, Bar, EmptyState, Skeleton } from "@/components/ui";
import Chronologie from "@/components/Chronologie";
import Plateau25D from "@/components/Plateau25D";
import { useTournees } from "@/hooks/useApi";
import { C } from "@/lib/theme";

export default function TourneesPage() {
  const { data: tournees, isLoading } = useTournees();
  return (
    <AppShell>
      <PageHeader title="Tournées" subtitle={tournees ? `${tournees.length} tournée(s) générée(s)` : "Chargement…"} />
      {isLoading ? <Skeleton h={200} />
        : !tournees?.length ? <Card><EmptyState icon="🚛" title="Aucune tournée" hint="Lancez une optimisation depuis l'onglet Optimisation." /></Card>
        : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {tournees.map((t) => (
              <Card key={t.id} style={{ borderLeft: `3px solid ${t.couleur}` }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                  <div style={{ fontWeight: 800, fontSize: 14 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: t.couleur, marginRight: 8 }} />
                    {t.chauffeur_nom || "Non assigné"} — {t.vehicule_immat}
                  </div>
                  <StatusChip s={t.statut} />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginBottom: 10 }}>
                  {[["Missions", t.nb_missions], ["Kilomètres", `${t.km} km`], ["CO₂", `${t.co2_kg} kg`], ["Départ", t.depart]].map(([l, v]) => (
                    <div key={l as string} style={{ textAlign: "center", padding: "8px", background: C.navyMid, borderRadius: 6 }}>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{v}</div>
                      <div style={{ fontSize: 10, color: C.textDim }}>{l}</div>
                    </div>
                  ))}
                </div>
                <Bar pct={t.taux_remplissage} />
                {t.explications && t.explications.length > 0 && (
                  <details style={{ marginTop: 12 }}>
                    <summary style={{ cursor: "pointer", fontSize: 12, color: C.orange, fontWeight: 600 }}>💬 Pourquoi cette tournée ?</summary>
                    <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
                      {t.explications.map((e, i) => (
                        <div key={i} style={{ display: "flex", gap: 8, marginBottom: 7 }}>
                          <span style={{ color: C.orange, flexShrink: 0 }}>→</span>
                          <span style={{ fontSize: 12, color: C.textMid }}>{e}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                {t.plateau && t.plateau.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <Plateau25D machines={t.plateau} taux={t.taux_remplissage} tourIndex={t.id} />
                  </div>
                )}
                {t.chronologie && t.chronologie.length > 0 && (
                  <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${C.border}` }}>
                    <Chronologie etapes={t.chronologie} dureeMin={t.duree_min} />
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
    </AppShell>
  );
}
