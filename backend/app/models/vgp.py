"""Registre VGP — machines, historique des contrôles, levées d'anomalie,
contrats de location.

La table `vgp` garde une ligne par machine (n° de parc) avec le DERNIER état
connu (cache d'affichage). La table `vgp_rapports` garde la trace de TOUTES
les vérifications successives : traçabilité réglementaire (registre de
sécurité) et historique consultable au scan du QR code.

Le QR code par machine est UNIQUE et permanent : il pointe vers la fiche
machine, dont le CONTENU VISIBLE dépend de qui scanne :

  • scan anonyme (chantier)  → statut VGP et rapports PUBLIÉS uniquement
  • scan avec code de contrat → + informations du contrat de location
  • interface interne (auth)  → tout, y compris les rapports en attente

PUBLICATION — un rapport déposé n'est pas immédiatement visible côté public.
Il entre dans l'historique interne et attend la décision du chef d'atelier.
Objectif métier : que le client ne découvre pas une anomalie avant que
l'atelier et le service commercial aient statué sur le rapatriement de la
machine.

LEVÉE D'ANOMALIE — acte par lequel le chef d'atelier déclare la réserve
corrigée, après réparation. Elle est nominative, datée, et peut porter une
pièce justificative. Une anomalie levée cesse de bloquer la machine, mais
reste visible dans l'historique : c'est ce qui donne sa valeur au registre
en cas de contrôle.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Vgp(Base, TimestampMixin):
    """Machine au registre — dernier état connu (cache d'affichage)."""

    __tablename__ = "vgp"

    id: Mapped[int] = mapped_column(primary_key=True)
    parc: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    machine_modele: Mapped[str | None] = mapped_column(String(120), nullable=True, default="")
    date_vgp: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observations: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    anomalie: Mapped[str | None] = mapped_column(String(5), nullable=True)  # OUI / NON

    # Identifiant opaque figurant dans le QR code, à la place du n° de parc.
    # Les n° de parc étant séquentiels, les exposer permettrait de parcourir
    # tout le parc machine en incrémentant l'URL. Le jeton est tiré au
    # hasard : il n'existe pas de « suivant » à essayer.
    jeton_public: Mapped[str | None] = mapped_column(String(16), unique=True,
                                                     nullable=True, index=True)

    # ── Dossier machine : trois documents ──
    fichier_vgp: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fichier_notice: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Fiche technique constructeur (dimensions, masses, capacités) — sert
    # aussi de référence à l'atelier lors d'une intervention.
    fichier_fiche_technique: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Carnet de maintenance — document exigible par le locataire au titre
    # des pièces remises à la mise à disposition (art. L4741-1).
    fichier_carnet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Photographie de la machine : permet à l'utilisateur de confirmer d'un
    # coup d'œil qu'il consulte bien la fiche de l'engin devant lui.
    fichier_photo: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VgpRapport(Base, TimestampMixin):
    """Un enregistrement par contrôle VGP — l'historique complet."""

    __tablename__ = "vgp_rapports"

    id: Mapped[int] = mapped_column(primary_key=True)
    parc: Mapped[str] = mapped_column(String(30), index=True)
    date_vgp: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observations: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    anomalie: Mapped[str | None] = mapped_column(String(5), nullable=True)  # OUI / NON
    fichier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organisme: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # SHA-256 du PDF — empêche la ré-insertion d'un rapport déjà présent
    # (double dépôt, re-test, double-clic).
    empreinte: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # ── Publication ──
    # Tant que publie=False, le rapport alimente l'historique interne mais
    # n'apparaît NI sur la fiche publique, NI dans le calcul du statut
    # affiché au scan. Seul un chef d'atelier peut publier.
    publie: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    publie_par: Mapped[str | None] = mapped_column(String(120), nullable=True)
    publie_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VgpLevee(Base, TimestampMixin):
    """Levée d'anomalie — déclaration nominative de correction d'une réserve.

    Un rapport peut recevoir plusieurs levées si plusieurs réserves sont
    traitées successivement. La machine est considérée débloquée lorsqu'une
    levée existe pour son dernier rapport en anomalie.
    """

    __tablename__ = "vgp_levees"

    id: Mapped[int] = mapped_column(primary_key=True)
    rapport_id: Mapped[int] = mapped_column(
        ForeignKey("vgp_rapports.id", ondelete="CASCADE"), index=True)
    # Dénormalisé pour interroger l'historique d'une machine sans jointure
    parc: Mapped[str] = mapped_column(String(30), index=True)

    date_levee: Mapped[date] = mapped_column(Date)
    # Nom de l'agent ayant procédé à la levée — renseigné depuis le compte
    # authentifié, jamais saisi librement.
    auteur: Mapped[str] = mapped_column(String(120))
    auteur_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Nature de l'intervention réalisée (obligatoire : c'est ce qui donne
    # sa valeur probante à la levée)
    description: Mapped[str] = mapped_column(Text)
    # Pièce justificative facultative : photo, bon de réparation, facture
    fichier: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VgpContrat(Base, TimestampMixin):
    """Contrat de location — données fournies par le service commercial.

    Porte un code d'accès aléatoire, propre à CE contrat : il permet au
    locataire de consulter les informations complètes de la machine pendant
    la durée de la location, et cesse de fonctionner à son terme.
    """

    __tablename__ = "vgp_contrats"

    id: Mapped[int] = mapped_column(primary_key=True)
    parc: Mapped[str] = mapped_column(String(30), index=True)
    numero_contrat: Mapped[str] = mapped_column(String(40), index=True)

    client_nom: Mapped[str] = mapped_column(String(160))
    chantier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ville: Mapped[str | None] = mapped_column(String(120), nullable=True)

    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Code d'accès aléatoire, unique. Alphabet sans caractères ambigus
    # (ni 0/O, ni 1/I/L) : il est destiné à être lu sur papier.
    code_acces: Mapped[str] = mapped_column(String(16), unique=True, index=True)

    # Permet de révoquer un code avant le terme du contrat sans supprimer
    # l'enregistrement (traçabilité).
    revoque: Mapped[bool] = mapped_column(Boolean, default=False)


class VgpCodeAgent(Base, TimestampMixin):
    """Code de service permettant aux agents Accès Industrie de consulter
    une machine depuis le QR code, sans passer par l'application.

    C'est un secret PARTAGÉ : non nominatif, il ne trace pas qui consulte.
    Il est donc révocable et destiné à être renouvelé périodiquement.
    Pour toute action engageante — publication, levée — le compte
    authentifié reste exigé : un code de service ne signe rien.

    Deux portées :
      • AGENCE  — rapports publiés, sur toutes les machines
      • ATELIER — tout, y compris les rapports en attente de traitement
    """

    __tablename__ = "vgp_codes_agent"

    id: Mapped[int] = mapped_column(primary_key=True)
    libelle: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    portee: Mapped[str] = mapped_column(String(12), default="AGENCE")  # AGENCE | ATELIER
    actif: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class VgpPrestataire(Base, TimestampMixin):
    """Organisme de contrôle réglementaire (CADET, AVGP, Apave…).

    Le rattachement d'une machine à un prestataire n'est pas automatique :
    c'est le chef d'atelier qui choisit, au moment de la demande, qui
    intervient sur quel chantier.
    """

    __tablename__ = "vgp_prestataires"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160))
    telephone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference_client: Mapped[str | None] = mapped_column(String(60), nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class VgpDemande(Base, TimestampMixin):
    """Demande d'intervention VGP — bon de commande adressé à un prestataire.

    Cycle : le système repère les échéances à 30 jours et propose ; le chef
    d'atelier choisit le prestataire et valide ; le bon est émis en PDF et
    envoyé par courriel. Aucune émission automatique : un bon de commande
    engage financièrement l'entreprise.
    """

    __tablename__ = "vgp_demandes"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    prestataire_id: Mapped[int] = mapped_column(
        ForeignKey("vgp_prestataires.id"), index=True)

    # BROUILLON | VALIDEE | ENVOYEE | ANNULEE
    statut: Mapped[str] = mapped_column(String(12), default="BROUILLON", index=True)

    cree_par: Mapped[str | None] = mapped_column(String(120), nullable=True)
    valide_par: Mapped[str | None] = mapped_column(String(120), nullable=True)
    valide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    envoye_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erreur_envoi: Mapped[str | None] = mapped_column(String(300), nullable=True)

    date_souhaitee: Mapped[date | None] = mapped_column(Date, nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    fichier_pdf: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VgpDemandeLigne(Base, TimestampMixin):
    """Une machine à contrôler dans une demande.

    Le lieu est figé au moment de la création : une machine sur chantier
    doit être contrôlée là où elle se trouve, et cette information peut
    changer avant l'intervention.
    """

    __tablename__ = "vgp_demandes_lignes"

    id: Mapped[int] = mapped_column(primary_key=True)
    demande_id: Mapped[int] = mapped_column(
        ForeignKey("vgp_demandes.id", ondelete="CASCADE"), index=True)
    parc: Mapped[str] = mapped_column(String(30), index=True)
    machine_modele: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_echeance: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Lieu d'intervention — chantier si la machine est en location, dépôt sinon
    lieu: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ville: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sur_chantier: Mapped[bool] = mapped_column(Boolean, default=False)
    numero_contrat: Mapped[str | None] = mapped_column(String(40), nullable=True)


class VgpAccesLog(Base, TimestampMixin):
    """Journal des tentatives d'accès par code de contrat.

    Double usage : limitation du nombre d'essais (un code court se devine
    par tâtonnement) et traçabilité des consultations.
    """

    __tablename__ = "vgp_acces_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    parc: Mapped[str] = mapped_column(String(30), index=True)
    code_tente: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    succes: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    contrat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # AUCUN | LOCATAIRE | AGENCE | ATELIER
    niveau: Mapped[str | None] = mapped_column(String(12), nullable=True)
