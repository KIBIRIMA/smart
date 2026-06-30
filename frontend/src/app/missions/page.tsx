"use client";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, StatusChip, TypeChip, EmptyState, Skeleton } from "@/components/ui";
import { useMissions } from "@/hooks/useApi";
import { C } from "@/lib/theme";

export default function MissionsPage() {
  const [statut, setStatut] = useState("");
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const qs = `?${new URLSearchParams({ ...(statut && { statut }), ...(type && { type_op: type }), ...(q && { q }) })}`;
  const { data: missions, isLoading } = useMissions(qs);

  return (
    <AppShell>
      <PageHeader title="Missions" subtitle={missions ? `${missions.length} mission(s)` : "Chargement…"} />
      <Card style={{ padding: "12px 14px", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 10 }}>
          <input placeholder="Rechercher client, adresse, machine…" value={q} onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1, maxWidth: 280, padding: "7px 11px", background: C.navyMid, border: `1px solid ${C.border}`, borderRadius: 7, color: C.text, fontSize: 12, outline: "none" }} />
          <select value={type} onChange={(e) => setType(e.target.value)} style={sel}>
            <option value="">Tous types</option><option value="livraison">Livraison</option><option value="recuperation">Récupération</option>
          </select>
          <select value={statut} onChange={(e) => setStatut(e.target.value)} style={sel}>
            <option value="">Tous statuts</option><option value="A_PLANIFIER">À planifier</option><option value="PLANIFIEE">Planifiée</option><option value="EN_COURS">En cours</option>
          </select>
        </div>
      </Card>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {isLoading ? <div style={{ padding: 16 }}><Skeleton h={200} /></div>
          : !missions?.length ? <EmptyState title="Aucune mission" hint="Ajustez vos filtres ou importez des missions." />
          : (
            <table>
              <thead><tr><th>Client</th><th>Adresse</th><th>Type</th><th>Machine</th><th>Qté</th><th>Statut</th></tr></thead>
              <tbody>
                {missions.map((m) => (
                  <tr key={m.id}>
                    <td style={{ fontWeight: 600 }}>{m.client_nom}</td>
                    <td style={{ color: C.textMid, fontSize: 11 }}>{m.adresse}</td>
                    <td><TypeChip t={m.type_op} /></td>
                    <td style={{ fontSize: 11 }}>{m.machine_modele}</td>
                    <td><span style={{ background: `${C.orange}20`, color: C.orange, padding: "1px 7px", borderRadius: 8, fontSize: 10, fontWeight: 700 }}>×{m.quantite}</span></td>
                    <td><StatusChip s={m.statut} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Card>
    </AppShell>
  );
}
const sel: React.CSSProperties = { width: 150, padding: "7px 11px", background: C.navyMid, border: `1px solid ${C.border}`, borderRadius: 7, color: C.text, fontSize: 12, outline: "none" };
