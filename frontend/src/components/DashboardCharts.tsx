"use client";
import { C } from "@/lib/theme";
import { Card } from "./ui";
import { Donut, Legend } from "./viz";
import { useHistory, useTournees, useMissions } from "@/hooks/useApi";
import type { Tournee, Mission } from "@/types";

/* ————————————————————————————————————————————————
   Bloc de graphes dashboard — branché sur les vraies données.
   - Barres par tournée         : useTournees()  (taux_remplissage réel)
   - Donut livraison/récup      : useMissions()  (type_op réel)
   - Courbe + cumul historique  : useHistory()   (auto-adaptatif, jamais de plantage)
   ———————————————————————————————————————————————— */

// —— Courbe lissée avec aire dégradée (façon inspiration) ——
function AreaLine({ points, color, w = 560, h = 150 }: { points: number[]; color: string; w?: number; h?: number }) {
  if (points.length < 2) return null;
  const pad = 8;
  const max = Math.max(...points) * 1.1 || 1;
  const px = (i: number) => pad + (w - pad * 2) * (i / (points.length - 1));
  const py = (v: number) => h - pad - (h - pad * 2) * (v / max);
  // courbe lissée (Catmull-Rom → Bézier)
  const pts = points.map((v, i) => [px(i), py(v)] as [number, number]);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x} ${c1y} ${c2x} ${c2y} ${p2[0]} ${p2[1]}`;
  }
  const area = `${d} L ${px(points.length - 1)} ${h - pad} L ${px(0)} ${h - pad} Z`;
  const gid = `grad-${color.replace("#", "")}`;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// —— Barres horizontales par tournée ——
function TourneeBars({ tournees }: { tournees?: Tournee[] }) {
  if (!tournees || tournees.length === 0)
    return <div style={{ fontSize: 12, color: C.textMid, padding: "20px 0" }}>Aucune tournée à afficher.</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {tournees.slice(0, 8).map((t, i) => {
        const pct = Math.min(100, t.taux_remplissage ?? 0);
        const col = pct > 85 ? C.green : pct > 60 ? C.warn : C.red;
        return (
          <div key={t.id ?? i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 11, color: C.textMid, width: 62, flexShrink: 0 }}>Tournée {i + 1}</span>
            <div style={{ flex: 1, height: 10, background: C.track, borderRadius: 999, overflow: "hidden" }}>
              <div style={{ width: `${pct}%`, height: "100%", background: col, borderRadius: 999, transition: "width .8s" }} />
            </div>
            <span style={{ fontSize: 11, fontWeight: 700, color: col, width: 34, textAlign: "right" }}>{Math.round(pct)}%</span>
          </div>
        );
      })}
    </div>
  );
}

// —— Donut répartition livraison / récupération ——
function TypeSplit({ missions }: { missions?: Mission[] }) {
  if (!missions || missions.length === 0)
    return <div style={{ fontSize: 12, color: C.textMid, padding: "20px 0" }}>Aucune mission.</div>;
  const liv = missions.filter((m) => m.type_op === "livraison").length;
  const rec = missions.length - liv;
  const pctLiv = Math.round((liv / missions.length) * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
      <Donut value={pctLiv} size={120} stroke={16} color={C.livraison} center={`${pctLiv}%`} sub="livraison" />
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: C.livraison }} />
          <span style={{ fontSize: 13, color: C.text }}>Livraisons <b>{liv}</b></span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: C.recuperation }} />
          <span style={{ fontSize: 13, color: C.text }}>Récupérations <b>{rec}</b></span>
        </div>
      </div>
    </div>
  );
}

// —— Historique auto-adaptatif : trace si possible, sinon message propre ——
type Pt = { km?: number; economies?: number; taux?: number };
function extractSeries(hist: unknown): { km: number[]; eco: number[]; cumulEco: number[] } | null {
  if (!Array.isArray(hist) || hist.length < 2) return null;
  const km: number[] = [], eco: number[] = [];
  for (const row of hist as Record<string, unknown>[]) {
    // mapping tolérant : on cherche les champs probables
    const k = Number(row.km ?? row.kilometres ?? row.distance ?? NaN);
    const e = Number(row.economies ?? row.economie ?? row.savings ?? row.gain ?? NaN);
    if (!Number.isNaN(k)) km.push(k);
    if (!Number.isNaN(e)) eco.push(e);
  }
  if (km.length < 2 && eco.length < 2) return null;
  let acc = 0;
  const cumulEco = eco.map((v) => (acc += v));
  return { km, eco, cumulEco };
}

function HistoryChart() {
  const { data: hist, isLoading } = useHistory();
  const series = extractSeries(hist);

  if (isLoading)
    return <div style={{ fontSize: 12, color: C.textMid, padding: "30px 0", textAlign: "center" }}>Chargement de l'historique…</div>;

  if (!series)
    return (
      <div style={{ textAlign: "center", padding: "34px 20px", color: C.textMid }}>
        <div style={{ fontSize: 26, marginBottom: 8 }}>📈</div>
        <div style={{ fontWeight: 600, fontSize: 13, color: C.text }}>Historique en cours de constitution</div>
        <div style={{ fontSize: 12, color: C.textDim, marginTop: 4 }}>
          La courbe apparaîtra dès que plusieurs optimisations auront été enregistrées.
        </div>
      </div>
    );

  return (
    <div>
      <div style={{ fontSize: 12, color: C.textMid, marginBottom: 6 }}>Kilomètres optimisés par exécution</div>
      <AreaLine points={series.km.length >= 2 ? series.km : series.eco} color={C.brand} />
      {series.cumulEco.length >= 2 && (
        <>
          <div style={{ fontSize: 12, color: C.textMid, margin: "14px 0 6px" }}>
            Économies cumulées depuis le début — <b style={{ color: C.green }}>{Math.round(series.cumulEco[series.cumulEco.length - 1]).toLocaleString("fr-FR")} €</b>
          </div>
          <AreaLine points={series.cumulEco} color={C.green} h={110} />
        </>
      )}
    </div>
  );
}

// —— Export : bloc complet à insérer dans le dashboard ——
export default function DashboardCharts({ tauxRemplissage }: { tauxRemplissage?: number }) {
  const { data: tournees } = useTournees();
  const { data: missions } = useMissions();
  const taux = Math.round(tauxRemplissage ?? 0);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
      {/* Grand donut remplissage mis en avant */}
      <Card style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: C.textFaint, alignSelf: "flex-start" }}>
          Taux de remplissage moyen
        </div>
        <Donut value={taux} size={168} stroke={20} color={taux >= 80 ? C.green : C.warn} center={`${taux}%`} sub="cible 80 %" />
        <div style={{ fontSize: 12, color: C.textMid, textAlign: "center" }}>
          {taux >= 80 ? "Objectif atteint" : "Sous l'objectif"} — sur {tournees?.length ?? "…"} tournées
        </div>
      </Card>

      {/* Répartition livraison / récup */}
      <Card>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: C.textFaint, marginBottom: 14 }}>
          Répartition des missions
        </div>
        <TypeSplit missions={missions} />
      </Card>

      {/* Barres par tournée */}
      <Card>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: C.textFaint, marginBottom: 14 }}>
          Remplissage par tournée
        </div>
        <TourneeBars tournees={tournees} />
      </Card>

      {/* Historique auto-adaptatif */}
      <Card>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: C.textFaint, marginBottom: 8 }}>
          Performance dans le temps
        </div>
        <HistoryChart />
      </Card>
    </div>
  );
}
