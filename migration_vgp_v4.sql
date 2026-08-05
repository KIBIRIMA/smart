-- ═══════════════════════════════════════════════════════════════════
--  Module VGP v3 — migration
--
--  À exécuter APRÈS migration_vgp_v2.sql, avant redémarrage du backend.
--
--    docker compose exec -T db psql -U smarttransport -d smarttransport \
--      < migration_vgp_v3.sql
--
--  Instructions idempotentes : réexécutable sans risque.
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

-- ── 1. Jeton opaque dans le QR code ─────────────────────────────────
-- Les n° de parc étant séquentiels, les exposer dans l'URL du QR
-- permettrait de parcourir tout le parc machine en incrémentant.
ALTER TABLE vgp
  ADD COLUMN IF NOT EXISTS jeton_public VARCHAR(16);

CREATE UNIQUE INDEX IF NOT EXISTS ix_vgp_jeton_public
  ON vgp (jeton_public) WHERE jeton_public IS NOT NULL;

-- Attribution d'un jeton aux machines existantes.
-- Alphabet sans caractères ambigus (ni O/I/L, ni 0/1) : le jeton peut
-- devoir être lu ou dicté.
UPDATE vgp
   SET jeton_public = (
     SELECT string_agg(
              substr('ABCDEFGHJKMNPQRSTUVWXYZ23456789',
                     (random() * 30)::int + 1, 1), '')
       FROM generate_series(1, 12)
   )
 WHERE jeton_public IS NULL;

-- ── 1 bis. Dossier machine : carnet de maintenance et photographie ──
ALTER TABLE vgp
  ADD COLUMN IF NOT EXISTS fichier_carnet VARCHAR(255),
  ADD COLUMN IF NOT EXISTS fichier_photo  VARCHAR(255);

-- ── 2. Prestataires de contrôle ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS vgp_prestataires (
    id               SERIAL PRIMARY KEY,
    nom              VARCHAR(120) NOT NULL,
    email            VARCHAR(160) NOT NULL,
    telephone        VARCHAR(30),
    reference_client VARCHAR(60),
    actif            BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vgp_prestataires_actif ON vgp_prestataires (actif);

-- Organismes déjà présents dans les rapports traités.
-- Les adresses sont à compléter avant la première utilisation.
INSERT INTO vgp_prestataires (nom, email, actif)
SELECT 'CADET (Cabinet Kupiec et Debergh)', 'a-renseigner@exemple.fr', TRUE
 WHERE NOT EXISTS (SELECT 1 FROM vgp_prestataires WHERE nom LIKE 'CADET%');
INSERT INTO vgp_prestataires (nom, email, actif)
SELECT 'AVGP CONTROLE', 'a-renseigner@exemple.fr', TRUE
 WHERE NOT EXISTS (SELECT 1 FROM vgp_prestataires WHERE nom LIKE 'AVGP%');

-- ── 3. Demandes d'intervention (bons de commande) ───────────────────
CREATE TABLE IF NOT EXISTS vgp_demandes (
    id             SERIAL PRIMARY KEY,
    reference      VARCHAR(40) NOT NULL UNIQUE,
    prestataire_id INTEGER     NOT NULL REFERENCES vgp_prestataires(id),
    statut         VARCHAR(12) NOT NULL DEFAULT 'BROUILLON',
    cree_par       VARCHAR(120),
    valide_par     VARCHAR(120),
    valide_le      TIMESTAMPTZ,
    envoye_le      TIMESTAMPTZ,
    erreur_envoi   VARCHAR(300),
    date_souhaitee DATE,
    commentaire    TEXT,
    fichier_pdf    VARCHAR(255),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vgp_demandes_statut       ON vgp_demandes (statut);
CREATE INDEX IF NOT EXISTS ix_vgp_demandes_prestataire  ON vgp_demandes (prestataire_id);

CREATE TABLE IF NOT EXISTS vgp_demandes_lignes (
    id             SERIAL PRIMARY KEY,
    demande_id     INTEGER     NOT NULL REFERENCES vgp_demandes(id) ON DELETE CASCADE,
    parc           VARCHAR(30) NOT NULL,
    machine_modele VARCHAR(120),
    date_echeance  DATE,
    lieu           VARCHAR(200),
    ville          VARCHAR(120),
    sur_chantier   BOOLEAN     NOT NULL DEFAULT FALSE,
    numero_contrat VARCHAR(40),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vgp_dl_demande ON vgp_demandes_lignes (demande_id);
CREATE INDEX IF NOT EXISTS ix_vgp_dl_parc    ON vgp_demandes_lignes (parc);

COMMIT;

-- ── Vérification ────────────────────────────────────────────────────
--   SELECT parc, jeton_public FROM vgp ORDER BY parc LIMIT 5;
--   SELECT count(*) FROM vgp WHERE jeton_public IS NULL;   -- doit valoir 0
--   SELECT nom, email FROM vgp_prestataires;
