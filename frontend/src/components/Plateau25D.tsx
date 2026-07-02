"use client";
import { useState, useMemo } from "react";
import { C } from "@/lib/theme";

export type PlateauMachine = {
  machine: string; client?: string; type?: string;
  longueur: number; largeur: number; poids: number;
  hauteur?: number; categorie?: string;
};

const PLATEAU = { longueur: 12.5, largeur: 2.55 };
const GAP = 0.15;
const FLECHE_LON_MIN = 5.0;

function categorie(m: PlateauMachine): string {
  if (m.categorie) return m.categorie;
  const n = m.machine.toUpperCase();
  if (/A ?38|ARTICUL|TOUCAN|ATN|ZEBRA|600AJ|460SJ|HA ?\d|HA20|MRT/.test(n)) return "articulée";
  if (/MT ?18|TELESCOP/.test(n)) return "articulée";
  return "ciseaux";
}
function aFleche(m: PlateauMachine): boolean {
  return categorie(m) === "articulée" && m.longueur >= FLECHE_LON_MIN;
}

type Placed = PlateauMachine & { x: number; y: number; w: number };

// Placement sur UN plateau : larges pleine largeur, étroites côte à côte (2 rangées)
function placer(ms: PlateauMachine[]): Placed[] {
  const ch: Placed[] = [];
  let xG = 0, xD = 0;
  const larges = ms.filter((m) => m.largeur > 1.275);
  const etroites = ms.filter((m) => m.largeur <= 1.275);
  for (const m of larges) {
    const x = Math.max(xG, xD);
    ch.push({ ...m, x, y: 0, w: PLATEAU.largeur });
    xG = x + m.longueur + GAP; xD = xG;
  }
  for (const m of etroites) {
    if (xG <= xD) { ch.push({ ...m, x: xG, y: 0, w: PLATEAU.largeur / 2 - 0.03 }); xG += m.longueur + GAP; }
    else { ch.push({ ...m, x: xD, y: PLATEAU.largeur / 2, w: PLATEAU.largeur / 2 - 0.03 }); xD += m.longueur + GAP; }
  }
  return ch;
}

type Vue = "iso" | "side" | "top";

export default function Plateau25D({ machines, taux, tourIndex }: {
  machines: PlateauMachine[]; taux: number; tourIndex?: number | string;
}) {
  const [vue, setVue] = useState<Vue>("iso");
  const [hover, setHover] = useState<number | null>(null);
  const placed = useMemo(() => placer(machines), [machines]);
  const lonMax = Math.max(PLATEAU.longueur, ...placed.map((c) => c.x + c.longueur));

  // échelles adaptées à chaque vue, compressées pour tenir dans le cadre
  const W = 760, Hsvg = vue === "top" ? 200 : 280;
  const scaleX = Math.min(vue === "iso" ? 50 : 56, (W - 160) / lonMax);

  function proj(x: number, y: number, z: number): [number, number] {
    if (vue === "iso") return [90 + x * scaleX - y * 0.4 * 28, 210 - z * 34 + y * 28 * 0.7];
    if (vue === "side") return [70 + x * scaleX, 230 - z * 42];
    return [70 + x * scaleX, 40 + y * 55]; // top
  }
  function shade(hex: string, d: number) {
    const c = parseInt(hex.slice(1), 16);
    const r = Math.max(0, Math.min(255, ((c >> 16) & 255) + d));
    const g = Math.max(0, Math.min(255, ((c >> 8) & 255) + d));
    const b = Math.max(0, Math.min(255, (c & 255) + d));
    return `rgb(${r},${g},${b})`;
  }

  function drawBox(c: Placed, i: number) {
    const cat = categorie(c);
    const isR = (c.type || "").startsWith("recup");
    const color = isR ? C.purple : (cat === "articulée" ? C.orange : "#2563EB");
    const dark = shade(color, -50), light = shade(color, 40);
    const h = 2.0 * 0.6;
    const dim = hover != null && hover !== i;
    const op = dim ? 0.35 : 1;
    const label = c.machine.split("(")[0].trim().slice(0, 12);
    const dims = `${c.longueur}×${c.largeur}m·${c.poids}t`;

    if (vue === "iso") {
      const p1 = proj(c.x, c.y, h), p2 = proj(c.x + c.longueur, c.y, h);
      const p3 = proj(c.x + c.longueur, c.y + c.w, h), p4 = proj(c.x, c.y + c.w, h);
      const p5 = proj(c.x, c.y, 0), p6 = proj(c.x + c.longueur, c.y, 0), p7 = proj(c.x + c.longueur, c.y + c.w, 0);
      const lx = (p1[0] + p3[0]) / 2, ly = (p1[1] + p3[1]) / 2;
      return (
        <g key={i} opacity={op} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ cursor: "pointer" }}>
          <polygon points={`${p2} ${p3} ${p7} ${p6}`} fill={dark} stroke={dark} strokeWidth="0.5" />
          <polygon points={`${p1} ${p2} ${p6} ${p5}`} fill={color} stroke={dark} strokeWidth="0.5" />
          <polygon points={`${p1} ${p2} ${p3} ${p4}`} fill={light} stroke={dark} strokeWidth="0.5" />
          <text x={lx} y={ly - 1} textAnchor="middle" fontSize="7" fontWeight="700" fill="#fff">{label}</text>
          <text x={lx} y={ly + 6} textAnchor="middle" fontSize="5" fill="rgba(255,255,255,0.85)">{dims}</text>
          {aFleche(c) && flecheIso(c, h)}
        </g>
      );
    }
    // side & top : rectangles
    const a = vue === "side" ? proj(c.x, 0, h) : proj(c.x, c.y, 0);
    const b = vue === "side" ? proj(c.x + c.longueur, 0, 0) : proj(c.x + c.longueur, c.y + c.w, 0);
    const rx = Math.min(a[0], b[0]), ry = Math.min(a[1], b[1]);
    const rw = Math.abs(b[0] - a[0]), rh = Math.abs(b[1] - a[1]);
    return (
      <g key={i} opacity={op} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ cursor: "pointer" }}>
        <rect x={rx} y={ry} width={rw} height={rh} fill={color} stroke={dark} strokeWidth="0.6" rx="1" />
        <text x={rx + rw / 2} y={ry + rh / 2 - 1} textAnchor="middle" fontSize="7" fontWeight="700" fill="#fff">{label}</text>
        <text x={rx + rw / 2} y={ry + rh / 2 + 7} textAnchor="middle" fontSize="5" fill="rgba(255,255,255,0.85)">{dims}</text>
        {vue === "side" && aFleche(c) && flecheSide(c, h)}
      </g>
    );
  }

  function flecheIso(c: Placed, h: number) {
    const xs = c.x + c.longueur * 0.05, xe = 0.2, yF = PLATEAU.largeur / 2 - 0.15;
    const pA = proj(xs, yF - 0.2, h), pB = proj(xe, yF - 0.2, h + 1.15);
    const pC = proj(xe, yF + 0.2, h + 1.15), pD = proj(xs, yF + 0.2, h);
    const mx = (pA[0] + pB[0]) / 2, my = (pA[1] + pB[1]) / 2 - 8;
    return (<g>
      <polygon points={`${pA} ${pB} ${pC} ${pD}`} fill="#FFA726" stroke="#BF360C" strokeWidth="1" opacity="0.9" />
      <text x={mx} y={my} textAnchor="middle" fontSize="7.5" fontWeight="700" fill="#FFA726">FLÈCHE 2,5D</text>
    </g>);
  }
  function flecheSide(c: Placed, h: number) {
    const a = proj(c.x + c.longueur * 0.05, 0, h), b = proj(0.2, 0, h + 1.15);
    return <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#FFA726" strokeWidth="4" strokeLinecap="round" opacity="0.9" />;
  }

  // plateau (sol)
  const plIso = [proj(0, 0, 0), proj(PLATEAU.longueur, 0, 0), proj(PLATEAU.longueur, PLATEAU.largeur, 0), proj(0, PLATEAU.largeur, 0)];
  const ordre = [...placed].map((c, i) => ({ c, i })).sort((a, b) =>
    vue === "iso" ? (b.c.x + b.c.longueur) - (a.c.x + a.c.longueur) : a.c.x - b.c.x);
  const tauxColor = taux >= 80 ? C.green : taux >= 60 ? C.yellow : C.orange;
  const btn = (v: Vue, lbl: string) => (
    <button onClick={() => setVue(v)} style={{
      padding: "4px 12px", fontSize: 11, fontWeight: 700, borderRadius: 6, cursor: "pointer",
      border: `1px solid ${vue === v ? C.orange : C.border}`,
      background: vue === v ? C.orange : "transparent", color: vue === v ? "#fff" : C.textMid,
    }}>{lbl}</button>
  );
  const dep = machines.filter((m) => !(m.type || "").startsWith("recup")).length;
  const rec = machines.length - dep;

  return (
    <div style={{ background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 14, padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 13, color: C.textMid, textTransform: "uppercase", letterSpacing: 1 }}>
            Chargement plateau 2,5D {tourIndex != null ? `— Tournée #${tourIndex}` : ""}
          </div>
          <div style={{ fontSize: 12, color: C.textDim }}>
            {dep} livraison{dep > 1 ? "s" : ""} · {rec} récupération{rec > 1 ? "s" : ""} · plateau {PLATEAU.longueur} m
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 34, fontWeight: 800, color: tauxColor, lineHeight: 1 }}>{taux}%</div>
          <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1 }}>Remplissage</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        {btn("iso", "ISO")}{btn("side", "LATÉRALE")}{btn("top", "DESSUS")}
      </div>

      <svg viewBox={`0 0 ${W} ${Hsvg}`} style={{ width: "100%", height: "auto", overflow: "visible" }}>
        {vue === "iso" && (
          <polygon points={plIso.map((p) => p.join(",")).join(" ")} fill="#0F1E33" stroke={C.orange} strokeWidth="1.2" opacity="0.85" />
        )}
        {vue === "side" && (() => { const a = proj(0, 0, 0), b = proj(PLATEAU.longueur, 0, 0); return <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={C.orange} strokeWidth="2" />; })()}
        {vue === "top" && (() => { const a = proj(0, 0, 0), b = proj(PLATEAU.longueur, PLATEAU.largeur, 0); return <rect x={a[0]} y={a[1]} width={b[0] - a[0]} height={b[1] - a[1]} fill="#0F1E33" stroke={C.orange} strokeWidth="1.2" opacity="0.85" />; })()}

        {/* repère 12.5m si dépassement */}
        {lonMax > PLATEAU.longueur && (() => {
          const a = proj(PLATEAU.longueur, 0, 0);
          const b = vue === "top" ? proj(PLATEAU.longueur, PLATEAU.largeur, 0) : proj(PLATEAU.longueur, vue === "iso" ? PLATEAU.largeur : 0, vue === "side" ? 2.2 : 0);
          return <><line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#EF4444" strokeWidth="1.5" strokeDasharray="4" /><text x={a[0]} y={a[1] - 4} fontSize="8" fill="#EF4444">12,5m</text></>;
        })()}

        {ordre.map(({ c, i }) => drawBox(c, i))}
      </svg>

      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11, color: C.textMid, flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 11, height: 11, background: "#2563EB", borderRadius: 2 }} /> Ciseaux</span>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 11, height: 11, background: C.orange, borderRadius: 2 }} /> Articulée (livraison)</span>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 11, height: 11, background: C.purple, borderRadius: 2 }} /> Récupération</span>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 11, height: 11, background: "#FFA726", borderRadius: 2 }} /> Flèche</span>
      </div>
    </div>
  );
}
