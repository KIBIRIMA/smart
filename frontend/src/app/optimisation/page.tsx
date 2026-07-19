"use client";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Bar, Spinner } from "@/components/ui";
import Plateau25D from "@/components/Plateau25D";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { OptimizeResult } from "@/types";

function hMin(min?: number | null): string {
  if (min == null) return "—";
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return `${h}h${String(m).padStart(2, "0")}`;
}

export default function OptimisationPage() {
  const [phase, setPhase] = useState<"config" | "running" | "results">("config");
  const [moteur, setMoteur] = useState("v12");
  const [fusion, setFusion] = useState(true);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"compare" | "tours" | "why">("compare");

  const run = async () => {
    if (phase === "running") return; // empêche les lancements multiples
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
            {[["Tournées", result.nb_tournees], ["Estimation initiale", result.nb_tournees_min_theorique],
              ["Kilomètres", `${result.km_total} km`], ["Taux moyen", `${result.taux_moyen}%`],
              ["Moteur", result.moteur], ["Calcul", `${result.duree_calcul_s}s`]].map(([l, v]) => (
              <Card key={l as string} style={{ flex: 1, minWidth: 120, textAlign: "center", padding: 12 }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: C.orange }}>{v}</div>
                <div style={{ fontSize: 10, color: C.textMid }}>{l}</div>
              </Card>
            ))}
          </div>

          {/* ENCART CHAUFFEURS-JOURNÉES (affecter_chauffeurs du moteur) */}
          {result.nb_chauffeurs != null && result.chauffeurs && result.chauffeurs.length > 0 && (
            <Card style={{ marginBottom: 14, borderLeft: `3px solid ${C.green}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>👥 Affectation chauffeurs</span>
                  <span style={{ fontSize: 12, color: C.textMid, marginLeft: 8 }}>
                    {result.nb_tournees} tournées regroupées en{" "}
                    <b style={{ color: C.green }}>{result.nb_chauffeurs} chauffeur{result.nb_chauffeurs > 1 ? "s" : ""}-journée{result.nb_chauffeurs > 1 ? "s" : ""}</b>
                    <span style={{ color: C.textDim }}> — durées pauses réglementaires incluses</span>
                  </span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 900, color: C.green }}>{result.nb_chauffeurs}</div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(210px,1fr))", gap: 8 }}>
                {result.chauffeurs.map((ch: any) => {
                  const dureeMin = ch.duree_avec_pauses_min ?? null;
                  const pct = ch.charge_pct_avec_pauses ?? ch.charge_pct;
                  const over = !!ch.depassement_8h;
                  const barColor = over ? C.red : pct > 95 ? C.orange : C.green;
                  return (
                    <div key={ch.id} style={{ padding: 10, background: C.navyMid, borderRadius: 8, border: over ? `1px solid ${C.red}` : "none" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 700 }}>{ch.nom}</span>
                        {over && <span style={{ fontSize: 10, fontWeight: 800, color: C.red }}>⚠ &gt; 8h</span>}
                      </div>
                      <div style={{ fontSize: 11, color: C.textMid }}>
                        Tournées : {ch.tours.join(" + ")}
                        {ch.fin_journee ? ` · fin ${ch.fin_journee}` : ""}
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 5 }}>
                        <span style={{ fontSize: 11, color: over ? C.red : pct > 95 ? C.orange : C.textMid }}>
                          {dureeMin != null ? hMin(dureeMin) : ch.duree_texte} / 8h
                        </span>
                        <span style={{ fontSize: 11, color: barColor, fontWeight: 700 }}>{pct}%</span>
                      </div>
                      <div style={{ height: 4, background: C.border, borderRadius: 2, marginTop: 4, overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${Math.min(100, pct)}%`, background: barColor }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {/* ENCART RENTABILITÉ (calcul_rentabilite du moteur) */}
          {result.rentabilite && (
            <Card style={{ marginBottom: 14, borderLeft: `3px solid ${C.orange}` }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>💰 Rentabilité de la journée</div>
              <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 10 }}>
                <div><div style={{ fontSize: 22, fontWeight: 800 }}>{result.rentabilite.ca_total_eur}€</div><div style={{ fontSize: 10, color: C.textMid }}>CA estimé</div></div>
                <div><div style={{ fontSize: 22, fontWeight: 800, color: C.textMid }}>{result.rentabilite.cout_total_eur}€</div><div style={{ fontSize: 10, color: C.textMid }}>Coût total</div></div>
                <div><div style={{ fontSize: 22, fontWeight: 800, color: C.green }}>{result.rentabilite.marge_total_eur}€</div><div style={{ fontSize: 10, color: C.textMid }}>Marge</div></div>
                <div><div style={{ fontSize: 22, fontWeight: 800, color: C.green }}>{result.rentabilite.taux_marge_pct}%</div><div style={{ fontSize: 10, color: C.textMid }}>Taux de marge</div></div>
              </div>
              {result.rentabilite.tournees_deficitaires && result.rentabilite.tournees_deficitaires.length > 0 && (
                <div style={{ fontSize: 12, color: C.red, padding: 8, background: `${C.red}15`, borderRadius: 6 }}>
                  ⚠ Tournée(s) déficitaire(s) : {result.rentabilite.tournees_deficitaires.join(", ")} — à mutualiser ou sous-traiter
                </div>
              )}
            </Card>
          )}

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
              {result.tournees.map((t: any) => (
                <Card key={t.index} style={{ borderLeft: `3px solid ${t.couleur}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, flexWrap: "wrap", gap: 6 }}>
                    <span style={{ fontWeight: 800 }}>
                      Tournée #{t.index}
                      {t.chauffeur && <span style={{ color: C.green, fontWeight: 700 }}> — {t.chauffeur}</span>}
                    </span>
                    <span style={{ fontSize: 12, color: C.textMid }}>
                      {t.nb_missions} missions · {t.km} km · {t.co2_kg} kg CO₂
                      {t.depart && <> · {t.depart} → {t.fin ?? "?"}</>}
                    </span>
                  </div>
                  {(t.conduite_min != null || t.pause_min != null) && (
                    <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                      {[["🚛 Conduite", hMin(t.conduite_min)], ["🔧 Manutention", hMin(t.manutention_min)],
                        ["⏸ Pauses", t.pause_min ? hMin(t.pause_min) : "aucune"]].map(([l, v]) => (
                        <span key={l as string} style={{ fontSize: 11, color: C.textMid, background: C.navyMid, borderRadius: 6, padding: "3px 9px" }}>
                          {l} : <b style={{ color: C.text }}>{v}</b>
                        </span>
                      ))}
                    </div>
                  )}
                  <Bar pct={t.taux_remplissage} />
                  {t.plateau && t.plateau.length > 0 && (
                    <div style={{ marginTop: 14 }}>
                      <Plateau25D
                        machines={t.plateau}
                        taux={t.taux_remplissage}
                        tourIndex={t.index}
                        plateauAller={t.plateau_aller}
                        plateauRetour={t.plateau_retour}
                        camion={t.camion}
                      />
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}

          {tab === "why" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
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
