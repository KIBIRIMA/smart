"use client";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Chip, EmptyState, Skeleton } from "@/components/ui";
import { useChauffeurs } from "@/hooks/useApi";
import { C } from "@/lib/theme";

export default function ChauffeursPage() {
  const { data, isLoading } = useChauffeurs();
  return (
    <AppShell>
      <PageHeader title="Chauffeurs" subtitle={data ? `${data.length} conducteurs` : "Chargement…"} />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {isLoading ? <div style={{ padding: 16 }}><Skeleton h={160} /></div>
          : !data?.length ? <EmptyState icon="👥" title="Aucun chauffeur" />
          : (
            <table>
              <thead><tr><th>Nom</th><th>Téléphone</th><th>Permis</th><th>Disponibilité</th></tr></thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 600 }}>{c.nom}</td>
                    <td style={{ color: C.textMid, fontFamily: "monospace" }}>{c.telephone}</td>
                    <td><Chip label={c.permis} color={C.purple} /></td>
                    <td><Chip label={c.disponible ? "Disponible" : "Indisponible"} color={c.disponible ? C.green : C.red} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Card>
    </AppShell>
  );
}
