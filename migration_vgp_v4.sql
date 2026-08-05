-- ═══════════════════════════════════════════════════════════════════
--  Module VGP v4 — migration (corrigée)
--
--  Remplace la version précédente, qui échouait : PostgreSQL n'évaluait
--  la sous-requête de génération du jeton qu'une seule fois, produisant
--  la même valeur pour toutes les machines et violant l'index unique.
--  La sous-requête est désormais corrélée à la ligne (v.id = v.id), ce
--  qui force son recalcul pour chacune.
--
--    docker compose exec -T db psql -U smarttransport -d smarttransport \
--      < migration_vgp_v4.sql
--
--  Idempotente : réexécutable sans risque.
--  Prérequis : migration_vgp_v2.sql déjà appliquée.
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

-- ── 1. Dossier machine : jeton opaque, carnet, photographie ─────────
ALTER TABLE vgp
  ADD COLUMN IF NOT EXISTS jeton_public   VARCHAR(16),
  ADD COLUMN IF NOT EXISTS fichier_carnet VARCHAR(255),
  ADD COLUMN IF NOT EXISTS fichier_photo  VARCHAR(255);

-- Attribution d'un jeton aux machines qui n'en ont pas.
-- Alphabet sans caractères ambigus (ni O/I/L, ni 0/1).
UPDATE vgp v
   SET jeton_public = (
     SELECT string_agg(
              substr('ABCDEFGHJKMNPQRSTUVWXYZ23456789',
                     (random() * 30)::int + 1, 1), '')
       FROM generate_series(1, 12) AS g(i)
      WHERE v.id = v.id
   )
 WHERE v.jeton_public IS NULL;

-- Filet de sécurité : reprise des collisions éventuelles avant la pose
-- de l'index unique.
UPDATE vgp v
   SET jeton_public = (
     SELECT string_agg(
              substr('ABCDEFGHJKMNPQRSTUVWXYZ23456789',
                     (random() * 30)::int + 1, 1), '')
       FROM generate_series(1, 12) AS g(i)
      WHERE v.id = v.id
   )
 WHERE v.id IN (
   SELECT id FROM (
     SELECT id, row_number() OVER (PARTITION BY jeton_public ORDER BY id) AS rang
       FROM vgp WHERE jeton_public IS NOT NULL
   ) d WHERE d.rang > 1
 );

CREATE UNIQUE INDEX IF NOT EXISTS ix_vgp_jeton_public
  ON vgp (jeton_public) WHERE jeton_public IS NOT NULL;

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

-- Organismes rencontrés dans les rapports déjà traités.
-- ⚠ Adresses à renseigner avant toute validation de demande.
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
CREATE INDEX IF NOT EXISTS ix_vgp_demandes_statut      ON vgp_demandes (statut);
CREATE INDEX IF NOT EXISTS ix_vgp_demandes_prestataire ON vgp_demandes (prestataire_id);

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

-- ── Vérification (à exécuter après) ─────────────────────────────────
--   SELECT count(*) AS total,
--          count(DISTINCT jeton_public) AS distincts,
--          count(*) FILTER (WHERE jeton_public IS NULL) AS manquants
--     FROM vgp;
--   → total = distincts, manquants = 0
