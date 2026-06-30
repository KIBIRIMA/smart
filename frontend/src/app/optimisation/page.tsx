"use client";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Bar, Spinner } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { OptimizeResult } from "@/types";

export default function OptimisationPage() {
  const [phase, setPhase] = useState<"config" | "running" | "results">("config");
  const [moteur, setMoteur] = useState("v12");
  const [fusion, setFusion] = useState(true);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"compare" | "tours" | "why">("compare");

  const run = async () => {
    setPhase("running"); setError("");
    try {
      const r = await apiFetch<OptimizeResult>("/optimizer/run", {
        method: "POST", body: JSON.stringify({ moteur, fusion }),
      });
      setResult(r); setPhase("results");
    } catch (e: any) { setError(e.message); setPhase("config"); }
  };

  return (
    <AppShell>
      <PageHeader title="Centre d'optimisation" subtitle="Moteur Smart Transport AI — OR-Tools VRP + Bin-Packing 2D"
        actions={phase === "results" ? (
          <>
            <button onClick={() => { setPhase("config"); setResult(null); }} style={btnGhost}>Nouvelle optimisation</button>
            <button onClick={() => {}} style={btnPrimary}>📤 Exporter</button>
          </>
        ) : undefined} />

      {error && <Card style={{ borderColor: C.red, marginBottom: 14 }}><span style={{ color: C.red, fontSize: 12 }}>⚠ {error}</span></Card>}

      {phase === "config" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>Paramètres</div>
            <label style={lbl}>Moteur d'optimisation</label>
            <select value={moteur} onChange={(e) => setMoteur(e.target.value)} style={sel}>
              <option value="v12">v12 — Recommandé (FFD + post-fusion)</option>
              <option value="v11">v11 — Stable</option>
            </select>
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16, cursor: "pointer", fontSize: 12, color: C.textMid }}>
              <input type="checkbox" checked={fusion} onChange={(e) => setFusion(e.target.checked)} style={{ width: 16, height: 16 }} />
              Activer les fusions de tournées sous-remplies (&lt;50%)
            </label>
            <button onClick={run} style={{ ...btnPrimary, width: "100%", marginTop: 20 }}>⚡ Lancer l'optimisation</button>
          </Card>
          <Card>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Missions à planifier</div>
            <div style={{ fontSize: 32, fontWeight: 900, color: C.orange }}>—</div>
            <p style={{ fontSize: 12, color: C.textMid, marginTop: 8 }}>
              Les missions au statut « À planifier » seront optimisées. Le moteur calcule le minimum
              de tournées en respectant les contraintes physiques de chargement plateau.
            </p>
          </Card>
        </div>
      )}

      {phase === "running" && (
        <Card style={{ padding: 48, textAlign: "center" }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}><Spinner size={36} /></div>
          <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 6 }}>Optimisation en cours…</div>
          <div style={{ fontSize: 12, color: C.textMid }}>OR-Tools VRP · Bin-Packing 2D FFD · Post-processing fusion</div>
        </Card>
      )}

      {phase === "results" && result && (
        <div className="fade-up">
          <div style={{ display: "flex", gap: 14, marginBottom: 14, flexWrap: "wrap" }}>
            {[["Tournées", result.nb_tournees], ["Min. théorique", result.nb_tournees_min_theorique],
              ["Kilomètres", `${result.km_total} km`], ["Taux moyen", `${result.taux_moyen}%`],
              ["Moteur", result.moteur], ["Calcul", `${result.duree_calcul_s}s`]].map(([l, v]) => (
              <Card key={l as string} style={{ flex: 1, minWidth: 120, textAlign: "center", padding: 12 }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: C.orange }}>{v}</div>
                <div style={{ fontSize: 10, color: C.textMid }}>{l}</div>
              </Card>
            ))}
          </div>

          <div style={{ display: "flex", gap: 3, background: C.bgCard, padding: 5, borderRadius: 9, border: `1px solid ${C.border}`, width: "fit-content", marginBottom: 14 }}>
            {[["compare", "🔄 Avant / Après"], ["tours", "🚛 Tournées"], ["why", "💬 Pourquoi ces tournées ?"]].map(([id, l]) => (
              <button key={id} onClick={() => setTab(id as any)} style={{
                padding: "6px 14px", borderRadius: 7, fontSize: 12, fontWeight: tab === id ? 700 : 500,
                background: tab === id ? C.orange : "transparent", color: tab === id ? "#fff" : C.textMid, border: "none", cursor: "pointer" }}>{l}</button>
            ))}
          </div>

          {tab === "compare" && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
              {result.comparaison.map((c) => (
                <Card key={c.label}>
                  <div style={{ fontSize: 11, color: C.textMid, marginBottom: 10 }}>{c.label}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span style={{ fontSize: 13, color: C.textDim, textDecoration: "line-through" }}>{c.avant}</span>
                    <span style={{ fontSize: 20, fontWeight: 900, color: C.green }}>{c.apres}</span>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 11, fontWeight: 700, color: C.green }}>{c.gain}</div>
                </Card>
              ))}
            </div>
          )}

          {tab === "tours" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {result.tournees.map((t) => (
                <Card key={t.index} style={{ borderLeft: `3px solid ${t.couleur}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                    <span style={{ fontWeight: 800 }}>Tournée #{t.index}</span>
                    <span style={{ fontSize: 12, color: C.textMid }}>{t.nb_missions} missions · {t.km} km · {t.co2_kg} kg CO₂</span>
                  </div>
                  <Bar pct={t.taux_remplissage} />
                </Card>
              ))}
            </div>
          )}

          {tab === "why" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <Card style={{ borderColor: `${C.purple}40`, background: `${C.purple}08` }}>
                <span style={{ fontSize: 12, color: C.textMid }}>💡 Chaque décision du moteur est tracée et expliquée en langage métier — transparence totale pour la DSI.</span>
              </Card>
              {result.tournees.map((t) => (
                <details key={t.index} style={{ background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 9, padding: 14 }}>
                  <summary style={{ cursor: "pointer", fontWeight: 700, display: "flex", justifyContent: "space-between" }}>
                    <span><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: t.couleur, marginRight: 8 }} />Tournée #{t.index} — {t.taux_remplissage}% remplissage</span>
                    <span style={{ color: C.orange, fontSize: 12 }}>▾ Voir le raisonnement</span>
                  </summary>
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
                    {t.explications.map((e, i) => (
                      <div key={i} style={{ display: "flex", gap: 9, marginBottom: 8 }}>
                        <span style={{ color: C.orange, flexShrink: 0 }}>→</span>
                        <span style={{ fontSize: 12, color: C.textMid, lineHeight: 1.5 }}>{e}</span>
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
const lbl: React.CSSProperties = { display: "block", fontSize: 11, color: C.textMid, marginBottom: 5 };
const sel: React.CSSProperties = { width: "100%", padding: "8px 11px", background: C.navyMid, border: `1px solid ${C.border}`, borderRadius: 7, color: C.text, fontSize: 12, outline: "none" };
const btnPrimary: React.CSSProperties = { padding: "8px 16px", borderRadius: 8, background: C.orange, color: "#fff", fontSize: 12, fontWeight: 700, border: "none", cursor: "pointer" };
const btnGhost: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, background: "transparent", color: C.textMid, fontSize: 12, border: `1px solid ${C.border}`, cursor: "pointer" };
