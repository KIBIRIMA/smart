// Design system — Smart Transport AI
// Refonte "clair marine + rouge" (Power BI), rétrocompatible.
//
// Les anciennes clés (navy, bg, bgCard, orange, text, green, red…) sont
// CONSERVÉES avec des valeurs claires : tous tes composants existants
// (ui.tsx, Sidebar, Navbar, Kpi, PageHeader) tournent sans changer d'API.
// De nouvelles clés (brand, card, accent, track, ok, warn, danger, ciseaux…)
// sont ajoutées pour les dataviz Power BI. TC et ROLE_LABEL préservés.

export const C = {
  // ————— Marque / marine (ex navy) —————
  navy:    "#0A2540", // sidebar, titres, marque
  navyMid: "#12325A",
  navyLt:  "#CBD5E8", // ⚠ réutilisé comme "piste" de barre dans ui.tsx → clair

  // ————— Orange métier (échéance / attention / livraison) —————
  orange:  "#E67A00",
  orangeL: "#FF8A3D",
  orangeD: "#BF360C",

  // ————— Surfaces (clair) —————
  bg:      "#F5F7FB", // fond app
  bgCard:  "#FFFFFF", // cartes
  bgHover: "#EEF1F7", // survol / zones creuses

  border:  "#E2E8F2",
  text:    "#0C1B2E", // texte principal (foncé sur clair)
  textMid: "#47566B", // AA 7.47:1 sur blanc
  textDim: "#64748B", // AA 4.76:1 sur blanc (était #8A99AD → 2.9:1, illisible)

  // ————— Codes métier —————
  green:  "#1B9E5A", // CONFORME
  yellow: "#E67A00", // échéance proche (aligné orange)
  red:    "#E63946", // ANOMALIE / alerte
  purple: "#7A4FBF", // récupération
  cyan:   "#0FB5A6", // (voir note TypeChip ci-dessous)

  // ————— Nouvelles clés Power BI —————
  brand:      "#0A2540",
  brandSoft:  "#12325A",
  brandFaint: "#E7EDF6",
  accent:     "#2E6BB8",
  bgSubtle:   "#EEF1F7",
  card:       "#FFFFFF",
  cardAlt:    "#FBFCFE",
  borderStrong: "#CBD5E8",
  track:      "#E9EEF6",
  textMut:    "#47566B",
  textFaint:  "#64748B",
  ok:     "#1B9E5A", okBg: "#E5F5EC",
  danger: "#E63946", dangerBg: "#FCE8EA",
  action: "#E63946", // action primaire (boutons) — remplace l'ancien C.orange décoratif
  warn:   "#E67A00", warnBg: "#FDF0E1",

  // Plateau 2.5D — 4 catégories (codes fixes)
  ciseaux:      "#1E4E8C",
  livraison:    "#E67A00",
  recuperation: "#7A4FBF",
  fleche:       "#0FB5A6",

  // Forme / typo
  shadow:   "0 1px 3px rgba(10,37,64,.06), 0 4px 16px rgba(10,37,64,.05)",
  shadowLg: "0 4px 24px rgba(10,37,64,.10)",
  radius:   12,
  radiusSm: 8,
  font: "'Inter','Segoe UI',system-ui,-apple-system,sans-serif",
  mono: "'JetBrains Mono','SF Mono',ui-monospace,monospace",
};

// Palette de séries pour graphes — recalibrée fond clair
export const TC = ["#0A2540", "#7A4FBF", "#0FB5A6", "#1B9E5A", "#E67A00", "#D63384", "#4C5FD5"];

export const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Administrateur", DSI: "DSI", EXPLOITANT: "Exploitant",
  CHEF_AGENCE: "Chef d'agence", LECTURE: "Lecture seule",
};
