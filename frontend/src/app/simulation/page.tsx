"use client";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Bar, Spinner } from "@/components/ui";
import Plateau25D from "@/components/Plateau25D";
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
  const [baseline, setBaseline] = useState<OptimizeResult | null>(null);
  const [error, setError] = useState("");

  const toggle = (arr: number[], set: (v: number[]) => void, id: number) =>
    set(arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);

  const addMission = () =>
    setNewMissions([...newMissions, { client: `Chantier urgent ${newMissions.length + 1}`, type_op: "livraison", lat: 48.8 + Math.random() * 0.1, lng: 2.3 + Math.random() * 0.2 }]);

  const simulate = async () => {
    setRunning(true); setError(""); setResult(null);
    try {
      const r = await apiFetch<OptimizeResult>("/optimizer/simulate", {
        method: "POST",
        body: JSON.stringify({
          moteur: "v11", fusion: true,
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

  // Résumé texte du scénario simulé
  const scenarioTags: string[] = [];
  if (camions > 0) scenarioTags.push(`+${camions} camion${camions > 1 ? "s" : ""}`);
  if (vehiculesOff.length) scenarioTags.push(`${vehiculesOff.length} véhicule(s) HS`);
  if (chauffeursOff.length) scenarioTags.push(`${chauffeursOff.length} chauffeur(s) absent(s)`);
  if (newMissions.length) scenarioTags.push(`${newMissions.length} mission(s) urgente(s)`);

  return (
    <AppShell>
      <PageHeader title="Simulation « what-if »" subtitle="Modifiez les contraintes et mesurez l'impact avant de décider" />
      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 16 }}>
        {/* Colonne contraintes */}
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
          <button onClick={simulate} disabled={running} style={{ padding: 12, borderRadius: 9, background: C.purple, color: "#fff", fontWeight: 700, fontSize: 13, border: "none", cursor: running ? "wait" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: running ? 0.7 : 1 }}>
            {running ? <><Spinner size={16} />Simulation en cours…</> : "🔮 Lancer le scénario"}
          </button>
        </div>

        {/* Colonne résultats */}
        <div>
          {error && <Card style={{ borderColor: C.red, marginBottom: 12 }}><span style={{ color: C.red, fontSize: 12 }}>⚠ {error}</span></Card>}
          {!result ? (
            <Card style={{ padding: 48, textAlign: "center", color: C.textMid }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🔮</div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Aucun scénario lancé</div>
              <div style={{ fontSize: 12 }}>Ajustez les contraintes à gauche puis lancez pour voir l'impact sur les tournées, les coûts et la faisabilité.</div>
            </Card>
          ) : (
            <div className="fade-up">
              {/* Bandeau scénario */}
              <Card style={{ marginBottom: 12, borderLeft: `3px solid ${C.purple}` }}>
                <div style={{ fontSize: 11, color: C.textMid, marginBottom: 6 }}>SCÉNARIO SIMULÉ</div>
                {scenarioTags.length ? (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {scenarioTags.map((t) => (
                      <span key={t} style={{ fontSize: 12, fontWeight: 700, padding: "4px 10px", borderRadius: 6, background: `${C.purple}22`, color: C.purple, border: `1px solid ${C.purple}` }}>{t}</span>
                    ))}
                  </div>
                ) : <span style={{ fontSize: 12, color: C.textDim }}>Conditions nominales (aucune contrainte modifiée)</span>}
              </Card>

              {/* KPI principaux */}
              <div style={{ display: "flex", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
                {[["Tournées", result.nb_tournees, ""], ["Kilomètres", result.km_total, "km"], ["Remplissage", result.taux_moyen, "%"], ["CO₂", result.co2_kg, "kg"]].map(([l, v, u]) => (
                  <Card key={l as string} style={{ flex: 1, minWidth: 110, textAlign: "center", padding: 14 }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: C.purple }}>{v}<span style={{ fontSize: 12 }}> {u}</span></div>
                    <div style={{ fontSize: 10, color: C.textMid, textTransform: "uppercase", letterSpacing: 1 }}>{l}</div>
                  </Card>
                ))}
              </div>

              {/* Impact avant/après avec variations */}
              <Card style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>📊 Impact vs planification manuelle</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
                  {result.comparaison.map((c) => {
                    const positif = (c.delta_pct ?? 0) <= 0 || /remplissage/i.test(c.label);
                    const col = positif ? C.green : C.orange;
                    return (
                      <div key={c.label} style={{ padding: 12, background: C.navyMid, borderRadius: 8 }}>
                        <div style={{ fontSize: 10, color: C.textMid }}>{c.label}</div>
                        <div style={{ fontSize: 12, color: C.textDim, textDecoration: "line-through" }}>{c.avant}</div>
                        <div style={{ fontSize: 16, fontWeight: 800, color: col, marginTop: 2 }}>{c.apres}</div>
                        <div style={{ fontSize: 11, color: col, fontWeight: 700 }}>{c.gain}</div>
                      </div>
                    );
                  })}
                </div>
              </Card>

              {/* Lecture métier */}
              <Card style={{ marginBottom: 12, background: C.navyMid }}>
                <div style={{ fontSize: 12, color: C.text, lineHeight: 1.6 }}>
                  💡 <b>Lecture :</b> avec ce scénario, l'exploitation nécessite <b style={{ color: C.orange }}>{result.nb_tournees} tournée{result.nb_tournees > 1 ? "s" : ""}</b> pour {result.nb_missions} missions,
                  soit un taux de remplissage moyen de <b style={{ color: result.taux_moyen >= 75 ? C.green : C.yellow }}>{result.taux_moyen}%</b>.
                  {result.taux_moyen < 60 && <span style={{ color: C.orange }}> Remplissage faible : des tournées pourraient être mutualisées.</span>}
                  {result.taux_moyen >= 80 && <span style={{ color: C.green }}> Excellente densité de chargement.</span>}
                </div>
              </Card>

              {/* Tournées avec plateau 2.5D */}
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {result.tournees.map((t) => (
                  <Card key={t.index} style={{ borderLeft: `3px solid ${t.couleur}`, padding: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                      <span style={{ fontWeight: 700, fontSize: 13 }}>Tournée #{t.index}</span>
                      <span style={{ fontSize: 11, color: C.textMid }}>{t.nb_missions} missions · {t.km} km · {t.co2_kg} kg CO₂</span>
                    </div>
                    <Bar pct={t.taux_remplissage} />
                    {t.plateau && t.plateau.length > 0 && (
                      <div style={{ marginTop: 12 }}>
                        <Plateau25D machines={t.plateau} taux={t.taux_remplissage} tourIndex={t.index} />
                      </div>
                    )}
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
