"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";

const DEMO = [
  { email: "admin@acces-industrie.fr", role: "Administrateur" },
  { email: "dsi@acces-industrie.fr", role: "DSI" },
  { email: "heinrich.weber@acces-industrie.fr", role: "Exploitant" },
  { email: "chef.ps@acces-industrie.fr", role: "Chef d'agence" },
  { email: "lecture@acces-industrie.fr", role: "Lecture seule" },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("heinrich.weber@acces-industrie.fr");
  const [password, setPassword] = useState("exploit123");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setLoading(true); setErr("");
    try { await login(email, password); router.replace("/dashboard"); }
    catch (e: any) { setErr(e.message || "Échec de connexion"); setLoading(false); }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, background: `radial-gradient(ellipse 60% 50% at 50% 0%,${C.navyMid}80,transparent)` }} />
      <div style={{ width: "100%", maxWidth: 410, position: "relative", zIndex: 1 }} className="fade-up">
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <div style={{ width: 48, height: 48, background: `linear-gradient(135deg,${C.orange},${C.orangeD})`, borderRadius: 12,
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, boxShadow: `0 0 30px ${C.orange}40` }}>🚛</div>
            <div style={{ textAlign: "left" }}>
              <div style={{ fontSize: 19, fontWeight: 900 }}>Smart Transport AI</div>
              <div style={{ fontSize: 10, color: C.orange, fontWeight: 700, letterSpacing: ".08em" }}>ACCÈS INDUSTRIE</div>
            </div>
          </div>
          <p style={{ color: C.textMid, fontSize: 12 }}>Plateforme de pilotage logistique</p>
        </div>
        <div style={{ background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 12, padding: 30 }}>
          <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4 }}>Connexion</div>
          <p style={{ color: C.textMid, fontSize: 11, marginBottom: 20 }}>Accès sécurisé · JWT · 5 rôles</p>
          <label style={{ display: "block", fontSize: 10, color: C.textMid, marginBottom: 5 }}>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} style={inp} />
          <label style={{ display: "block", fontSize: 10, color: C.textMid, margin: "14px 0 5px" }}>Mot de passe</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()} style={inp} />
          {err && <div style={{ marginTop: 12, padding: "8px 12px", background: `${C.red}15`, border: `1px solid ${C.red}40`, borderRadius: 7, fontSize: 11, color: C.red }}>{err}</div>}
          <button onClick={submit} disabled={loading} style={{
            width: "100%", marginTop: 18, padding: 12, borderRadius: 9, background: C.orange, color: "#fff",
            fontWeight: 700, fontSize: 13, border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 9 }}>
            {loading ? <><Spinner size={16} />Authentification…</> : "Se connecter"}
          </button>
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
            <p style={{ fontSize: 10, color: C.textDim, marginBottom: 8 }}>Comptes de démonstration (cliquer pour pré-remplir) :</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {DEMO.map((d) => (
                <button key={d.email} onClick={() => { setEmail(d.email); setPassword(d.email.split("@")[0].includes("admin") ? "admin123" : d.email.split("@")[0].includes("dsi") ? "dsi123" : d.email.includes("chef") ? "chef123" : d.email.includes("lecture") ? "lecture123" : "exploit123"); }}
                  style={{ fontSize: 10, padding: "4px 9px", background: C.navyMid, border: `1px solid ${C.border}`, borderRadius: 6, color: C.textMid, cursor: "pointer" }}>
                  {d.role}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
const inp: React.CSSProperties = { width: "100%", padding: "9px 11px", background: C.navyMid, border: `1px solid ${C.border}`, borderRadius: 7, color: C.text, fontSize: 12, outline: "none" };
