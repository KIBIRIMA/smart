"use client";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Chip, EmptyState, Skeleton } from "@/components/ui";
import { useVehicules } from "@/hooks/useApi";
import { C } from "@/lib/theme";

export default function VehiculesPage() {
  const { data, isLoading } = useVehicules();
  return (
    <AppShell>
      <PageHeader title="Flotte de véhicules" subtitle={data ? `${data.length} camions plateau` : "Chargement…"} />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {isLoading ? <div style={{ padding: 16 }}><Skeleton h={200} /></div>
          : !data?.length ? <EmptyState icon="🚚" title="Aucun véhicule" />
          : (
            <table>
              <thead><tr><th>Immatriculation</th><th>Libellé</th><th>Plateau</th><th>Charge utile</th><th>Conso.</th><th>Statut</th></tr></thead>
              <tbody>
                {data.map((v) => (
                  <tr key={v.id}>
                    <td style={{ fontWeight: 600, fontFamily: "monospace" }}>{v.immatriculation}</td>
                    <td style={{ color: C.textMid }}>{v.libelle}</td>
                    <td style={{ fontSize: 11 }}>{v.plateau_longueur_m} × {v.plateau_largeur_m} m</td>
                    <td>{v.charge_utile_kg.toLocaleString("fr-FR")} kg</td>
                    <td>{v.conso_l_100km} L/100</td>
                    <td><Chip label={v.disponible ? "Disponible" : "Indispo."} color={v.disponible ? C.green : C.red} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Card>
    </AppShell>
  );
}
