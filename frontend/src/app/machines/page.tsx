"use client";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Chip, EmptyState, Skeleton } from "@/components/ui";
import { useMachines } from "@/hooks/useApi";
import { C } from "@/lib/theme";

export default function MachinesPage() {
  const { data, isLoading } = useMachines();
  return (
    <AppShell>
      <PageHeader title="Catalogue machines" subtitle={data ? `${data.length} modèles · dimensions constructeur réelles` : "Chargement…"} />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {isLoading ? <div style={{ padding: 16 }}><Skeleton h={200} /></div>
          : !data?.length ? <EmptyState icon="🏗️" title="Catalogue vide" />
          : (
            <table>
              <thead><tr><th>Modèle</th><th>Constructeur</th><th>Famille</th><th>L × l × h (m)</th><th>Poids</th></tr></thead>
              <tbody>
                {data.map((m) => (
                  <tr key={m.id}>
                    <td style={{ fontWeight: 600 }}>{m.modele}</td>
                    <td style={{ color: C.textMid }}>{m.constructeur}</td>
                    <td><Chip label={m.famille} color={m.famille === "nacelle" ? C.cyan : C.orange} /></td>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>{m.longueur_m} × {m.largeur_m} × {m.hauteur_m}</td>
                    <td>{m.poids_kg.toLocaleString("fr-FR")} kg</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Card>
    </AppShell>
  );
}
