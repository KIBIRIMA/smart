"use client";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import KpiGrid from "@/components/Kpi";
import { Card, StatusChip, Bar, EmptyState, Skeleton } from "@/components/ui";
import { useKpi, useTournees, useMissions } from "@/hooks/useApi";
import { C } from "@/lib/theme";
import Link from "next/link";

export default function DashboardPage() {
  const { data: kpi, isLoading: kl } = useKpi();
  const { data: tournees } = useTournees();
  const { data: missions } = useMissions("?statut=A_PLANIFIER");

  return (
    <AppShell>
      <PageHeader title="Tableau de bord" subtitle="Pilotage de l'exploitation en temps réel — Agence Paris Sud"
        actions={<Link href="/optimisation" style={btnPrimary}>⚡ Lancer une optimisation</Link>} />

      <KpiGrid kpi={kpi} loading={kl} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 14 }}>
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>🚛 Tournées actives</div>
          {!tournees ? <Skeleton h={120} /> : tournees.length === 0 ? (
            <EmptyState icon="🗺️" title="Aucune tournée planifiée" hint="Lancez une optimisation pour générer les tournées du jour." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {tournees.map((t) => (
                <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 5, height: 30, borderRadius: 3, background: t.couleur }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{t.chauffeur_nom || "Non assigné"} · {t.vehicule_immat}</div>
                    <div style={{ fontSize: 10, color: C.textMid }}>{t.nb_missions} missions · {t.km} km · {t.co2_kg} kg CO₂</div>
                  </div>
                  <div style={{ width: 110 }}><Bar pct={t.taux_remplissage} /></div>
                  <StatusChip s={t.statut} />
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>
            ⏳ Missions à planifier {missions && <span style={{ color: C.orange }}>({missions.length})</span>}
          </div>
          {!missions ? <Skeleton h={120} /> : missions.length === 0 ? (
            <EmptyState icon="✅" title="Tout est planifié" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {missions.slice(0, 6).map((m) => (
                <div key={m.id} style={{ padding: "9px 12px", background: C.bgHover, borderRadius: 8, border: `1px solid ${C.border}` }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{m.client_nom}</div>
                  <div style={{ fontSize: 10, color: C.textMid }}>{m.machine_modele} · {m.type_op}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
const btnPrimary: React.CSSProperties = { padding: "8px 16px", borderRadius: 8, background: C.orange, color: "#fff", fontSize: 12, fontWeight: 700, border: "none", cursor: "pointer" };
