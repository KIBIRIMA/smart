"use client";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, EmptyState, Skeleton } from "@/components/ui";
import { useClients } from "@/hooks/useApi";
import { C } from "@/lib/theme";

export default function ClientsPage() {
  const { data, isLoading } = useClients();
  return (
    <AppShell>
      <PageHeader title="Clients" subtitle={data ? `${data.length} comptes` : "Chargement…"} />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {isLoading ? <div style={{ padding: 16 }}><Skeleton h={160} /></div>
          : !data?.length ? <EmptyState icon="🏢" title="Aucun client" />
          : (
            <table>
              <thead><tr><th>Nom</th><th>Adresse</th><th>Code postal</th><th>Ville</th><th>Géocodé</th></tr></thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 600 }}>{c.nom}</td>
                    <td style={{ color: C.textMid }}>{c.adresse}</td>
                    <td style={{ fontFamily: "monospace" }}>{c.code_postal}</td>
                    <td>{c.ville}</td>
                    <td>{c.lat ? "✅" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Card>
    </AppShell>
  );
}
