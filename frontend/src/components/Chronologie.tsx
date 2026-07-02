"use client";
import { C } from "@/lib/theme";

export type Etape = {
  heure: string; lieu: string; action: string;
  machine?: string; duree_min?: number;
};

export default function Chronologie({ etapes, dureeMin }: { etapes: Etape[]; dureeMin?: number }) {
  if (!etapes || etapes.length === 0) return null;

  const couleurAction = (action: string) => {
    if (/départ/i.test(action)) return C.cyan;
    if (/retour/i.test(action)) return C.green;
    if (/récup/i.test(action)) return C.purple;
    return C.orange; // livraison
  };
  const icone = (action: string) => {
    if (/départ/i.test(action)) return "🏁";
    if (/retour/i.test(action)) return "🏠";
    if (/récup/i.test(action)) return "📥";
    return "📤";
  };

  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>🕒 Chronologie de la tournée</span>
        {dureeMin != null && (
          <span style={{ fontSize: 12, color: C.textMid }}>
            Durée : <b style={{ color: dureeMin <= 480 ? C.green : C.red }}>{Math.floor(dureeMin / 60)}h{String(dureeMin % 60).padStart(2, "0")}</b>
            <span style={{ color: C.textDim }}> / 8h max</span>
          </span>
        )}
      </div>
      <div style={{ position: "relative", paddingLeft: 8 }}>
        {/* ligne verticale */}
        <div style={{ position: "absolute", left: 15, top: 8, bottom: 8, width: 2, background: C.border }} />
        {etapes.map((e, i) => {
          const col = couleurAction(e.action);
          return (
            <div key={i} style={{ display: "flex", gap: 12, marginBottom: 14, position: "relative" }}>
              <div style={{
                width: 16, height: 16, borderRadius: "50%", background: col, flexShrink: 0,
                marginTop: 2, zIndex: 1, border: `2px solid ${C.bgCard}`,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 8,
              }} />
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                  <span style={{ fontSize: 13, fontWeight: 800, color: col, fontVariantNumeric: "tabular-nums" }}>{e.heure}</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{icone(e.action)} {e.action}</span>
                  {e.duree_min ? <span style={{ fontSize: 10, color: C.textDim }}>({e.duree_min} min)</span> : null}
                </div>
                <div style={{ fontSize: 11, color: C.textMid, marginTop: 1 }}>{e.lieu}</div>
                {e.machine ? <div style={{ fontSize: 11, color: C.orange, marginTop: 1 }}>⚙ {e.machine}</div> : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
