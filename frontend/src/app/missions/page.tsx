"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, StatusChip, TypeChip, EmptyState, Skeleton, Spinner } from "@/components/ui";
import { useMissions } from "@/hooks/useApi";
import { API, tokens } from "@/lib/api";
import { C } from "@/lib/theme";

export default function MissionsPage() {
  const router = useRouter();
  const [statut, setStatut] = useState("");
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const qs = `?${new URLSearchParams({ ...(statut && { statut }), ...(type && { type_op: type }), ...(q && { q }) })}`;
  const { data: missions, isLoading, mutate } = useMissions(qs);

  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ importees: number; geocodage: any; message: string } | null>(null);
  const [error, setError] = useState("");

  const onPick = () => fileInput.current?.click();

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true); setError(""); setResult(null);
    try {
      const form = new FormData();
      form.append("file", f);
      const res = await fetch(`${API}/import/missions?remplacer=true`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tokens.access}` },
        body: form,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Erreur ${res.status}`);
      }
      const data = await res.json();
      setResult(data);
      mutate();
    } catch (err: any) {
      setError(err.message || "Échec de l'import");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <AppShell>
      <PageHeader
        title="Missions"
        subtitle={missions ? `${missions.length} mission(s)` : "Chargement…"}
        actions={
          <>
            <input ref={fileInput} type="file" accept=".csv,text/csv" onChange={onFile} style={{ display: "none" }} />
            <button onClick={onPick} disabled={uploading} style={btnImport}>
              {uploading ? <><Spinner size={14} /> Import…</> : <>📥 Importer un CSV</>}
            </button>
            <button onClick={() => router.push("/optimisation")} style={btnPrimary}>⚡ Optimiser</button>
          </>
        }
      />

      {result && (
        <Card style={{ borderColor: `${C.green}50`, background: `${C.green}10`, marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20 }}>✅</span>
            <div>
              <div style={{ fontWeight: 700, color: C.green }}>{result.message}</div>
              <div style={{ fontSize: 11, color: C.textMid, marginTop: 2 }}>
                Géolocalisation : {result.geocodage.api || 0} par adresse précise, {result.geocodage.ville || 0} par ville.
                {" "}Va dans <b style={{ color: C.orange, cursor: "pointer" }} onClick={() => router.push("/optimisation")}>Optimisation</b> pour générer les tournées.
              </div>
            </div>
          </div>
        </Card>
      )}
      {error && (
        <Card style={{ borderColor: C.red, marginBottom: 12 }}>
          <span style={{ color: C.red, fontSize: 12 }}>⚠ {error}</span>
        </Card>
      )}

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
          : !missions?.length ? <EmptyState title="Aucune mission" hint="Importez un CSV ou ajustez vos filtres." />
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
const btnPrimary: React.CSSProperties = { padding: "8px 16px", borderRadius: 8, background: C.orange, color: "#fff", fontSize: 12, fontWeight: 700, border: "none", cursor: "pointer" };
const btnImport: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 16px", borderRadius: 8, background: C.bgHover, color: C.text, fontSize: 12, fontWeight: 600, border: `1px solid ${C.border}`, cursor: "pointer" };
