"use client";
import AppShell from "@/components/AppShell";
import PageHeader from "@/components/PageHeader";
import { Card, Chip } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";
import { C, ROLE_LABEL } from "@/lib/theme";

const MODULES_FUTURS = [
  { icon: "🔗", nom: "Intégration ERP / TMS", desc: "Connecteur ORTEC, SAP — synchronisation bidirectionnelle des missions", statut: "Prévu" },
  { icon: "🛡️", nom: "VGP & conformité", desc: "Suivi des vérifications générales périodiques par machine", statut: "Prévu" },
  { icon: "🔧", nom: "Maintenance prédictive", desc: "Alertes sur compteurs horaires et cycles d'entretien", statut: "Étude" },
  { icon: "📊", nom: "Business Intelligence", desc: "Tableaux de bord multi-agences, export Power BI", statut: "Prévu" },
  { icon: "🧠", nom: "IA prédictive", desc: "Prévision de demande et pré-affectation des tournées", statut: "Recherche" },
  { icon: "📱", nom: "Application mobile chauffeur", desc: "Feuille de route, signature électronique, photos", statut: "Prévu" },
];

export default function ParametresPage() {
  const { user } = useAuth();
  return (
    <AppShell>
      <PageHeader title="Paramètres" subtitle="Compte, plateforme et feuille de route produit" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 16 }}>
        <Card>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>👤 Mon compte</div>
          {user && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[["Nom", user.full_name], ["Email", user.email], ["Rôle", ROLE_LABEL[user.role]]].map(([l, v]) => (
                <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: C.textMid }}>{l}</span><span style={{ fontWeight: 600 }}>{v}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>⚙️ Plateforme</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[["Moteur d'optimisation", "v12 (OR-Tools)"], ["Base de données", "PostgreSQL"], ["Cache", "Redis"], ["Version", "1.0.0"]].map(([l, v]) => (
              <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: C.textMid }}>{l}</span><span style={{ fontWeight: 600, color: C.green }}>{v}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>🚀 Modules à venir</div>
        <p style={{ fontSize: 12, color: C.textMid, marginBottom: 16 }}>
          Smart Transport AI est conçu pour s'intégrer progressivement au système d'information du groupe.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
          {MODULES_FUTURS.map((m) => (
            <div key={m.nom} style={{ padding: 14, background: C.bgHover, border: `1px solid ${C.border}`, borderRadius: 9 }}>
              <div style={{ fontSize: 22, marginBottom: 8 }}>{m.icon}</div>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{m.nom}</div>
              <div style={{ fontSize: 11, color: C.textMid, marginBottom: 10, lineHeight: 1.5 }}>{m.desc}</div>
              <Chip label={m.statut} color={m.statut === "Prévu" ? C.orange : m.statut === "Étude" ? C.yellow : C.purple} />
            </div>
          ))}
        </div>
      </Card>
    </AppShell>
  );
}
