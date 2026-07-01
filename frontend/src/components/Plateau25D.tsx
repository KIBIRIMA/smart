"use client";
import { useState, useMemo } from "react";
import { C } from "@/lib/theme";

// ─────────────────────────────────────────────────────────────
//  Plateau 2.5D — vue isométrique du chargement d'un camion.
//  Innovation : la FLÈCHE TÉLESCOPIQUE des nacelles articulées
//  passe en superposition AÉRIENNE au-dessus des ciseaux, ce qui
//  récupère l'espace en hauteur et densifie le chargement.
// ─────────────────────────────────────────────────────────────

export type PlateauMachine = {
  machine: string;
  client?: string;
  type?: string;
  longueur: number;   // m
  largeur: number;    // m
  poids: number;      // t
  hauteur?: number;   // m (optionnel)
  categorie?: string; // ciseaux | mat | articulée
};

const PLATEAU = { longueur: 12.5, largeur: 2.55, hauteur: 3.0 };

// Devine la catégorie depuis le nom si non fournie (articulée = nacelle à bras)
function categorie(m: PlateauMachine): string {
  if (m.categorie) return m.categorie;
  const n = m.machine.toUpperCase();
  if (/\bA\s?38|A38|600AJ|460SJ|ARTICUL|TOUCAN|ATN|ZEBRA/.test(n)) return "articulée";
  if (/MRT|MT\s?18|MANITOU\s?M|TELESCOP/.test(n)) return "articulée";
  return "ciseaux";
}
// Une nacelle n'a une FLÈCHE DÉBORDANTE que si elle est assez grande (≥ 5 m
// repliée) : les grandes nacelles articulées (JLG 460, 600AJ, MRT…) posent
// leur flèche au-dessus des ciseaux. Les compactes (A 38 E, 4,1 m) tiennent
// repliées sans dépassement → pas de flèche dessinée.
const FLECHE_LON_MIN = 5.0;
function aFleche(m: PlateauMachine): boolean {
  return categorie(m) === "articulée" && m.longueur >= FLECHE_LON_MIN;
}
function flecheDe(m: PlateauMachine) {
  return { flecheLon: m.longueur * 1.1, flecheHaut: 0.65 };
}

type Placed = PlateauMachine & {
  x: number; y_pos: "gauche" | "droite" | "centre"; estArticulee: boolean;
  horsPlateau?: boolean;
};

// Répartit les machines sur un ou plusieurs plateaux (camions).
// Chaque plateau suit la stratégie 2.5D : ciseaux côte à côte, articulée(s)
// en fin avec flèche aérienne. Dès qu'une machine ne rentre plus, on ouvre
// un nouveau plateau (2e camion) — rien ne déborde du cadre.
const GAP = 0.25;

function placerSurUnPlateau(machines: PlateauMachine[]): { placed: Placed[]; reste: PlateauMachine[] } {
  const chargement: Placed[] = [];
  const reste: PlateauMachine[] = [];
  const ciseaux = machines.filter((m) => categorie(m) !== "articulée");
  const articulees = machines.filter((m) => categorie(m) === "articulée");
  const ordre = [...ciseaux, ...articulees];
  let xArt: number | null = null;

  for (const m of ordre) {
    const estArt = categorie(m) === "articulée";
    if (estArt) {
      if (xArt === null) {
        const xMaxCiseaux = chargement
          .filter((c) => !c.estArticulee)
          .reduce((s, c) => Math.max(s, c.x + c.longueur), 0);
        xArt = xMaxCiseaux + GAP;
      }
      if (xArt + m.longueur > PLATEAU.longueur + 0.01) { reste.push(m); continue; }
      chargement.push({ ...m, x: xArt, y_pos: "centre", estArticulee: true });
      xArt += m.longueur + GAP;
      continue;
    }
    // ciseau : tente côte à côte
    let placed = false;
    for (const p of chargement) {
      if (p.estArticulee || p.y_pos !== "gauche") continue;
      const cote = chargement.find((c) => c.x === p.x && c.y_pos === "droite");
      if (!cote && p.largeur + m.largeur <= PLATEAU.largeur) {
        chargement.push({ ...m, x: p.x, y_pos: "droite", estArticulee: false });
        placed = true; break;
      }
    }
    if (!placed) {
      const totalLon = chargement
        .filter((c) => !c.estArticulee && c.y_pos === "gauche")
        .reduce((s, c) => Math.max(s, c.x + c.longueur + GAP), 0);
      if (totalLon + m.longueur > PLATEAU.longueur + 0.01) { reste.push(m); continue; }
      chargement.push({ ...m, x: totalLon, y_pos: "gauche", estArticulee: false });
    }
  }
  return { placed: chargement, reste };
}

// Répartit sur autant de plateaux que nécessaire.
function repartirPlateaux(machines: PlateauMachine[]): Placed[][] {
  const plateaux: Placed[][] = [];
  let aPlacer = machines;
  let garde = 0;
  while (aPlacer.length > 0 && garde < 10) {
    const { placed, reste } = placerSurUnPlateau(aPlacer);
    if (placed.length === 0) break; // sécurité : une machine seule ne rentre nulle part
    plateaux.push(placed);
    aPlacer = reste;
    garde++;
  }
  return plateaux;
}

// Projection isométrique (reprise de la démo, recadrée pour le composant)
function projIso(x: number, y: number, z: number): [number, number] {
  const sx = 52, sy = 28, sz = 38;
  return [70 + x * sx - y * 0.4 * sy, 175 - z * sz + y * sy * 0.7];
}

function shade(hex: string, d: number) {
  const c = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.min(255, ((c >> 16) & 255) + d));
  const g = Math.max(0, Math.min(255, ((c >> 8) & 255) + d));
  const b = Math.max(0, Math.min(255, (c & 255) + d));
  return `rgb(${r},${g},${b})`;
}

function Box3D({ x, y, z, lon, larg, haut, color, label, dims }: any) {
  const p1 = projIso(x, y, z + haut), p2 = projIso(x + lon, y, z + haut);
  const p3 = projIso(x + lon, y + larg, z + haut), p4 = projIso(x, y + larg, z + haut);
  const p5 = projIso(x, y, z), p6 = projIso(x + lon, y, z), p7 = projIso(x + lon, y + larg, z);
  const light = shade(color, 40), dark = shade(color, -50);
  const lx = (p1[0] + p3[0]) / 2, ly = (p1[1] + p3[1]) / 2;
  return (
    <g>
      <polygon points={`${p1} ${p2} ${p6} ${p5}`} fill={color} stroke={dark} strokeWidth="0.5" />
      <polygon points={`${p2} ${p3} ${p7} ${p6}`} fill={dark} stroke={dark} strokeWidth="0.5" />
      <polygon points={`${p1} ${p2} ${p3} ${p4}`} fill={light} stroke={dark} strokeWidth="0.5" />
      {label && <text x={lx} y={ly - 1} textAnchor="middle" fontSize="8" fontWeight="700" fill="#fff">{label}</text>}
      {dims && <text x={lx} y={ly + 7} textAnchor="middle" fontSize="5.5" fill="rgba(255,255,255,0.85)">{dims}</text>}
    </g>
  );
}

// Dessine UN plateau (un camion) avec ses machines et flèches.
function PlateauSVG({ chargement, camionNum, total }: {
  chargement: Placed[]; camionNum: number; total: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const pl = [projIso(0, 0, 0), projIso(PLATEAU.longueur, 0, 0),
    projIso(PLATEAU.longueur, PLATEAU.largeur, 0), projIso(0, PLATEAU.largeur, 0)];
  const ordreRender = [...chargement].map((c, i) => ({ c, i }))
    .sort((a, b) => (b.c.x + b.c.longueur) - (a.c.x + a.c.longueur));

  // remplissage de ce plateau (longueur occupée / longueur plateau)
  const lonOcc = chargement.reduce((s, c) => Math.max(s, c.x + c.longueur), 0);
  const rempl = Math.round((lonOcc / PLATEAU.longueur) * 100);
  const rColor = rempl >= 80 ? C.green : rempl >= 60 ? C.yellow : C.orange;

  return (
    <div style={{ marginTop: camionNum > 1 ? 10 : 0 }}>
      {total > 1 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: C.text }}>
            🚛 Camion {camionNum} / {total}
          </span>
          <span style={{ fontSize: 12, color: rColor, fontWeight: 700 }}>{rempl}% rempli</span>
        </div>
      )}
      <svg viewBox="0 0 820 300" style={{ width: "100%", height: "auto", overflow: "visible" }}>
        <polygon points={pl.map((p) => p.join(",")).join(" ")} fill="#0F1E33" stroke={C.orange} strokeWidth="1.2" opacity="0.85" />
        <text x={pl[0][0]} y={pl[0][1] + 16} fontSize="9" fill={C.textDim}>0 m</text>
        <text x={pl[1][0] - 26} y={pl[1][1] + 16} fontSize="9" fill={C.textDim}>12,5 m</text>

        {ordreRender.map(({ c, i }) => {
          const cat = categorie(c);
          const isRecup = (c.type || "").startsWith("recup");
          const baseColor = isRecup ? C.purple : (cat === "articulée" ? C.orange : "#2563EB");
          const haut = (c.hauteur || 2.1) * (c.estArticulee ? 0.6 : 0.75);
          const yOff = c.y_pos === "droite" ? PLATEAU.largeur / 2 : 0;
          const larg = c.y_pos === "centre" ? PLATEAU.largeur - 0.1 : PLATEAU.largeur / 2 - 0.05;
          const y = c.estArticulee ? 0.05 : yOff + 0.05;
          const dim = hover != null && hover !== i;

          return (
            <g key={i} opacity={dim ? 0.35 : 1}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              style={{ cursor: "pointer", transition: "opacity .15s" }}>
              <Box3D x={c.x} y={y} z={0} lon={c.longueur}
                larg={c.estArticulee ? PLATEAU.largeur - 0.1 : larg}
                haut={haut} color={baseColor}
                label={c.machine.split("(")[0].trim().slice(0, 12)}
                dims={`${c.longueur}×${c.largeur}m · ${c.poids}t`} />

              {aFleche(c) && (() => {
                const f = flecheDe(c);
                const xStart = c.x + c.longueur * 0.05;
                const xEnd = 0.2;
                const yF = PLATEAU.largeur / 2 - 0.15;
                const zStart = haut;
                const zEnd = haut + f.flecheHaut + 0.5;
                const pA = projIso(xStart, yF - 0.2, zStart);
                const pB = projIso(xEnd, yF - 0.2, zEnd);
                const pC = projIso(xEnd, yF + 0.2, zEnd);
                const pD = projIso(xStart, yF + 0.2, zStart);
                const mx = (pA[0] + pB[0]) / 2, my = (pA[1] + pB[1]) / 2 - 10;
                return (
                  <g>
                    <polygon points={`${pA} ${pB} ${pC} ${pD}`}
                      fill="#FFA726" stroke="#BF360C" strokeWidth="1" opacity="0.9" />
                    <text x={mx} y={my} textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#FFA726">
                      FLÈCHE TÉLESCOPIQUE 2,5D
                    </text>
                  </g>
                );
              })()}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function Plateau25D({ machines, taux, tourIndex }: {
  machines: PlateauMachine[]; taux: number; tourIndex?: number | string;
}) {
  const plateaux = useMemo(() => repartirPlateaux(machines), [machines]);
  const tauxColor = taux >= 80 ? C.green : taux >= 60 ? C.yellow : C.orange;
  const nbCamions = plateaux.length;

  return (
    <div style={{ background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 14, padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <div>
          <div style={{ fontSize: 13, color: C.textMid, textTransform: "uppercase", letterSpacing: 1 }}>
            Chargement plateau 2,5D {tourIndex != null ? `— Tournée #${tourIndex}` : ""}
          </div>
          <div style={{ fontSize: 12, color: C.textDim }}>
            {machines.length} machines · superposition flèche télescopique · plateau {PLATEAU.longueur} m
          </div>
          {nbCamions > 1 && (
            <div style={{ fontSize: 11, color: C.orange, marginTop: 3, fontWeight: 600 }}>
              📦 Chargement réparti sur {nbCamions} camions — capacité d'un plateau dépassée
            </div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 40, fontWeight: 800, color: tauxColor, lineHeight: 1 }}>{taux}%</div>
          <div style={{ fontSize: 11, color: C.textDim, textTransform: "uppercase", letterSpacing: 1 }}>Remplissage</div>
        </div>
      </div>

      {plateaux.map((p, i) => (
        <PlateauSVG key={i} chargement={p} camionNum={i + 1} total={nbCamions} />
      ))}

      <div style={{ display: "flex", gap: 18, marginTop: 6, fontSize: 12, color: C.textMid, flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 12, height: 12, background: "#2563EB", borderRadius: 2 }} /> Ciseaux
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 12, height: 12, background: C.orange, borderRadius: 2 }} /> Nacelle articulée
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 12, height: 12, background: "#FFA726", borderRadius: 2 }} /> Flèche (zone aérienne)
        </span>
        <span style={{ color: C.textDim, marginLeft: "auto" }}>La flèche récupère l'espace au-dessus des ciseaux</span>
      </div>
    </div>
  );
}
