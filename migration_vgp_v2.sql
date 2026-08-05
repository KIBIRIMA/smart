-- ═══════════════════════════════════════════════════════════════════
--  Module VGP v2 — migration
--
--  À exécuter AVANT le redémarrage du backend avec le nouveau modèle.
--
--    docker compose exec db psql -U smarttransport -d smarttransport \
--      -f /dev/stdin < migration_vgp_v2.sql
--
--  ou en collant le contenu dans une session psql.
--
--  Toutes les instructions sont idempotentes : réexécutable sans risque.
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

-- ── 1. Machine : troisième document du dossier ──────────────────────
ALTER TABLE vgp
  ADD COLUMN IF NOT EXISTS fichier_fiche_technique VARCHAR(255);

-- ── 2. Rapports : dédup, organisme, publication ─────────────────────
ALTER TABLE vgp_rapports
  ADD COLUMN IF NOT EXISTS empreinte  VARCHAR(64),
  ADD COLUMN IF NOT EXISTS organisme  VARCHAR(30),
  ADD COLUMN IF NOT EXISTS publie     BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS publie_par VARCHAR(120),
  ADD COLUMN IF NOT EXISTS publie_le  TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_vgp_rapports_empreinte ON vgp_rapports (empreinte);
CREATE INDEX IF NOT EXISTS ix_vgp_rapports_publie    ON vgp_rapports (publie);

-- Reprise de l'existant : les rapports déjà en base ont été déposés avant
-- la notion de publication et sont déjà visibles au scan. On les considère
-- publiés pour ne pas faire disparaître d'information en production.
-- ⚠ Si l'on préfère repartir d'un registre entièrement à valider par
--    l'atelier, commenter la ligne ci-dessous.
UPDATE vgp_rapports
   SET publie = TRUE, publie_par = 'reprise migration', publie_le = NOW()
 WHERE publie = FALSE;

-- ── 3. Levées d'anomalie ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vgp_levees (
    id          SERIAL PRIMARY KEY,
    rapport_id  INTEGER NOT NULL REFERENCES vgp_rapports(id) ON DELETE CASCADE,
    parc        VARCHAR(30)  NOT NULL,
    date_levee  DATE         NOT NULL,
    auteur      VARCHAR(120) NOT NULL,
    auteur_id   INTEGER,
    description TEXT         NOT NULL,
    fichier     VARCHAR(255),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vgp_levees_rapport ON vgp_levees (rapport_id);
CREATE INDEX IF NOT EXISTS ix_vgp_levees_parc    ON vgp_levees (parc);

-- ── 4. Contrats de location ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vgp_contrats (
    id             SERIAL PRIMARY KEY,
    parc           VARCHAR(30)  NOT NULL,
    numero_contrat VARCHAR(40)  NOT NULL,
    client_nom     VARCHAR(160) NOT NULL,
    chantier       VARCHAR(200),
    ville          VARCHAR(120),
    date_debut     DATE         NOT NULL,
    date_fin       DATE,
    code_acces     VARCHAR(16)  NOT NULL UNIQUE,
    revoque        BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vgp_contrats_parc   ON vgp_contrats (parc);
CREATE INDEX IF NOT EXISTS ix_vgp_contrats_numero ON vgp_contrats (numero_contrat);
CREATE INDEX IF NOT EXISTS ix_vgp_contrats_code   ON vgp_contrats (code_acces);

-- ── 5. Journal des accès par code ───────────────────────────────────
CREATE TABLE IF NOT EXISTS vgp_acces_log (
    id         SERIAL PRIMARY KEY,
    parc       VARCHAR(30) NOT NULL,
    code_tente VARCHAR(16),
    ip         VARCHAR(45),
    succes     BOOLEAN     NOT NULL DEFAULT FALSE,
    contrat_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vgp_acces_parc   ON vgp_acces_log (parc);
CREATE INDEX IF NOT EXISTS ix_vgp_acces_succes ON vgp_acces_log (succes);

-- ── 6. Codes de service des agents Accès Industrie ──────────────────
CREATE TABLE IF NOT EXISTS vgp_codes_agent (
    id         SERIAL PRIMARY KEY,
    libelle    VARCHAR(120) NOT NULL,
    code       VARCHAR(24)  NOT NULL UNIQUE,
    portee     VARCHAR(12)  NOT NULL DEFAULT 'AGENCE',
    actif      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vgp_codes_agent_code  ON vgp_codes_agent (code);
CREATE INDEX IF NOT EXISTS ix_vgp_codes_agent_actif ON vgp_codes_agent (actif);

ALTER TABLE vgp_acces_log
  ADD COLUMN IF NOT EXISTS niveau VARCHAR(12);

COMMIT;

-- ── Vérification ────────────────────────────────────────────────────
--   \d vgp_rapports
--   \d vgp_levees
--   \d vgp_contrats
--   SELECT count(*) FILTER (WHERE publie) AS publies,
--          count(*) FILTER (WHERE NOT publie) AS en_attente
--     FROM vgp_rapports;
