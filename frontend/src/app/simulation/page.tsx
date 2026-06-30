"use client";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Bar, Spinner } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useChauffeurs, useVehicules } from "@/hooks/useApi";
import { C } from "@/lib/theme";
import type { OptimizeResult } from "@/types";

export default function SimulationPage() {
  const { data: chauffeurs } = useChauffeurs();
  const { data: vehicules } = useVehicules();

  const [camions, setCamions] = useState(0);
  const [chauffeursOff, setChauffeursOff] = useState<number[]>([]);
  const [vehiculesOff, setVehiculesOff] = useState<number[]>([]);
  const [newMissions, setNewMissions] = useState<{ client: string; type_op: string; lat: number; lng: number }[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [error, setError] = useState("");

  const toggle = (arr: number[], set: (v: number[]) => void, id: number) =>
    set(arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);

  const addMission = () =>
    setNewMissions([...newMissions, { client: `Chantier simulé ${newMissions.length + 1}`, type_op: "livraison", lat: 48.8 + Math.random() * 0.1, lng: 2.3 + Math.random() * 0.2 }]);

  const simulate = async () => {
    setRunning(true); setError(""); setResult(null);
    try {
      const r = await apiFetch<OptimizeResult>("/optimizer/simulate", {
        method: "POST",
        body: JSON.stringify({
          moteur: "v12", fusion: true,
          constraints: {
            camions_supplementaires: camions,
            chauffeurs_indisponibles: chauffeursOff,
            vehicules_indisponibles: vehiculesOff,
            nouvelles_missions: newMissions,
          },
        }),
      });
      setResult(r);
    } catch (e: any) { setError(e.message); }
    finally { setRunning(false); }
  };

  return (
    <AppShell>
      <PageHeader title="Simulation « what-if »" subtitle="Modifiez les contraintes et relancez l'optimisation pour mesurer l'impact" />
      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>🚚 Flotte</div>
            <label style={lbl}>Camions supplémentaires : <b style={{ color: C.orange }}>{camions}</b></label>
            <input type="range" min={0} max={10} value={camions} onChange={(e) => setCamions(+e.target.value)} style={{ width: "100%", accentColor: C.orange }} />
            <div style={{ fontSize: 11, color: C.textMid, marginTop: 12, marginBottom: 6 }}>Véhicules indisponibles :</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {(vehicules || []).map((v) => (
                <button key={v.id} onClick={() => toggle(vehiculesOff, setVehiculesOff, v.id)} style={pill(vehiculesOff.includes(v.id), C.red)}>{v.immatriculation}</button>
              ))}
            </div>
          </Card>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>👥 Chauffeurs indisponibles</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {(chauffeurs || []).map((c) => (
                <button key={c.id} onClick={() => toggle(chauffeursOff, setChauffeursOff, c.id)} style={pill(chauffeursOff.includes(c.id), C.red)}>{c.nom}</button>
              ))}
            </div>
          </Card>
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 700 }}>➕ Missions urgentes</span>
              <button onClick={addMission} style={{ ...pill(false, C.orange), borderColor: C.orange, color: C.orange }}>+ Ajouter</button>
            </div>
            {newMissions.length === 0 ? <span style={{ fontSize: 11, color: C.textDim }}>Aucune mission simulée</span> : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {newMissions.map((m, i) => (
                  <div key={i} style={{ fontSize: 11, padding: "6px 9px", background: C.bgHover, borderRadius: 6, display: "flex", justifyContent: "space-between" }}>
                    <span>{m.client}</span>
                    <button onClick={() => setNewMissions(newMissions.filter((_, j) => j !== i))} style={{ background: "none", border: "none", color: C.red, cursor: "pointer" }}>✕</button>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <button onClick={simulate} disabled={running} style={{ padding: 12, borderRadius: 9, background: C.purple, color: "#fff", fontWeight: 700, fontSize: 13, border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            {running ? <><Spinner size={16} />Simulation…</> : "🔮 Relancer l'optimisation"}
          </button>
        </div>

        <div>
          {error && <Card style={{ borderColor: C.red, marginBottom: 12 }}><span style={{ color: C.red, fontSize: 12 }}>⚠ {error}</span></Card>}
          {!result ? (
            <Card style={{ padding: 48, textAlign: "center", color: C.textMid }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🔮</div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Scénario non lancé</div>
              <div style={{ fontSize: 12 }}>Ajustez les contraintes à gauche puis relancez pour voir l'impact sur les tournées.</div>
            </Card>
          ) : (
            <div className="fade-up">
              <div style={{ display: "flex", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
                {[["Tournées", result.nb_tournees], ["Kilomètres", `${result.km_total} km`], ["Taux moyen", `${result.taux_moyen}%`], ["CO₂", `${result.co2_kg} kg`]].map(([l, v]) => (
                  <Card key={l as string} style={{ flex: 1, minWidth: 110, textAlign: "center", padding: 12 }}>
                    <div style={{ fontSize: 18, fontWeight: 800, color: C.purple }}>{v}</div>
                    <div style={{ fontSize: 10, color: C.textMid }}>{l}</div>
                  </Card>
                ))}
              </div>
              <Card style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Impact vs planification classique</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
                  {result.comparaison.map((c) => (
                    <div key={c.label} style={{ padding: 10, background: C.navyMid, borderRadius: 7 }}>
                      <div style={{ fontSize: 10, color: C.textMid }}>{c.label}</div>
                      <div style={{ fontSize: 15, fontWeight: 800, color: C.green, marginTop: 4 }}>{c.apres}</div>
                      <div style={{ fontSize: 10, color: C.green }}>{c.gain}</div>
                    </div>
                  ))}
                </div>
              </Card>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {result.tournees.map((t) => (
                  <Card key={t.index} style={{ borderLeft: `3px solid ${t.couleur}`, padding: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                      <span style={{ fontWeight: 700, fontSize: 12 }}>Tournée #{t.index}</span>
                      <span style={{ fontSize: 11, color: C.textMid }}>{t.nb_missions} missions · {t.km} km</span>
                    </div>
                    <Bar pct={t.taux_remplissage} />
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
const lbl: React.CSSProperties = { display: "block", fontSize: 11, color: C.textMid, marginBottom: 8 };
const pill = (active: boolean, color: string): React.CSSProperties => ({
  fontSize: 10, padding: "4px 9px", borderRadius: 6, cursor: "pointer",
  background: active ? `${color}22` : C.navyMid, border: `1px solid ${active ? color : C.border}`,
  color: active ? color : C.textMid, fontWeight: active ? 700 : 400,
});
