"""
Seed initial — crée le schéma et insère un jeu de données réaliste Accès Industrie.
Idempotent : ne réinsère pas si des utilisateurs existent déjà.
Lancé automatiquement au démarrage du conteneur backend (voir entrypoint).
"""
import asyncio
from datetime import date

from sqlalchemy import select
from app.db.session import engine, AsyncSessionLocal
from app.models import (Base, User, Agence, Client, Machine, Vehicule,
                        Chauffeur, Mission)
from app.core.security import hash_password
from app.core.roles import Role


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if existing:
            print("Seed ignoré — données déjà présentes.")
            return

        # ── Agence (dépôt) ──
        agence = Agence(nom="Paris Sud — Lieusaint", code="PS-77",
                        adresse="ZI de Lieusaint, 77550", lat=48.632, lng=2.470)
        db.add(agence); await db.flush()

        # ── Utilisateurs (5 rôles) ──
        users = [
            ("admin@acces-industrie.fr", "Administrateur Système", Role.ADMIN, "admin123"),
            ("dsi@acces-industrie.fr", "Direction SI", Role.DSI, "dsi123"),
            ("heinrich.weber@acces-industrie.fr", "Heinrich Weber", Role.EXPLOITANT, "exploit123"),
            ("chef.ps@acces-industrie.fr", "Chef Agence Paris Sud", Role.CHEF_AGENCE, "chef123"),
            ("lecture@acces-industrie.fr", "Consultation", Role.LECTURE, "lecture123"),
        ]
        for email, name, role, pwd in users:
            db.add(User(email=email, full_name=name, role=role.value,
                        hashed_password=hash_password(pwd), agence_id=agence.id))

        # ── Machines (extrait catalogue réel) ──
        machines_data = [
            ("Haulotte HA20RTJ", "Haulotte", "nacelle", 8.13, 2.30, 2.49, 9700),
            ("Haulotte HA16RTJ", "Haulotte", "nacelle", 6.96, 2.30, 2.30, 7300),
            ("Haulotte H12SX", "Haulotte", "nacelle", 5.42, 2.20, 2.30, 4900),
            ("JLG 460SJ", "JLG", "nacelle", 7.62, 2.49, 2.59, 8400),
            ("JLG 800AJ", "JLG", "nacelle", 11.40, 2.49, 3.00, 14500),
            ("Manitou MRT 2150", "Manitou", "telescopique", 7.20, 2.50, 3.10, 11900),
            ("Manitou MRT 1745", "Manitou", "telescopique", 6.40, 2.42, 2.95, 9800),
            ("Manitou 180ATJ", "Manitou", "nacelle", 9.00, 2.40, 2.90, 13000),
            ("Genie Z-60", "Genie", "nacelle", 7.30, 2.49, 2.59, 9650),
            ("Skyjack SJ63AJ", "Skyjack", "nacelle", 8.10, 2.49, 2.79, 9530),
        ]
        machines = []
        for mod, c, fam, l, w, h, p in machines_data:
            m = Machine(modele=mod, constructeur=c, famille=fam,
                        longueur_m=l, largeur_m=w, hauteur_m=h, poids_kg=p)
            db.add(m); machines.append(m)
        await db.flush()
        mby = {m.modele: m.id for m in machines}

        # ── Véhicules ──
        for immat, lib in [("AB-123-CD", "Plateau 13.6m #1"), ("EF-456-GH", "Plateau 13.6m #2"),
                           ("IJ-789-KL", "Plateau 13.6m #3"), ("MN-012-OP", "Plateau 13.6m #4"),
                           ("QR-345-ST", "Plateau 13.6m #5")]:
            db.add(Vehicule(immatriculation=immat, libelle=lib, agence_id=agence.id))

        # ── Chauffeurs ──
        for nom, tel, dispo in [("Marc Durand", "0612345678", True), ("Sophie Martin", "0623456789", True),
                                ("Patrick Lebrun", "0634567890", True), ("Nathalie Roy", "0645678901", True),
                                ("François Petit", "0656789012", True), ("Paul Moreau", "0667890123", False)]:
            db.add(Chauffeur(nom=nom, telephone=tel, disponible=dispo, agence_id=agence.id))

        # ── Clients ──
        clients_data = [
            ("Bouygues Construction", "15 rue du Faubourg", "93200", "Saint-Denis", 48.936, 2.355),
            ("Vinci Facilities", "8 av. de la République", "75011", "Paris", 48.861, 2.372),
            ("Eiffage Génie Civil", "Zone Industrielle", "77200", "Torcy", 48.753, 2.649),
            ("GTM Bâtiment", "12 rue Henri Barbusse", "92110", "Clichy", 48.902, 2.310),
            ("Léon Grosse", "45 bd Gal de Gaulle", "94120", "Fontenay", 48.775, 2.480),
            ("Colas Île-de-France", "3 allée des Chênes", "91300", "Massy", 48.726, 2.274),
            ("NGE Construction", "27 rue de la Paix", "78000", "Versailles", 48.805, 2.130),
            ("Spie Batignolles", "89 av. Aristide Briand", "92160", "Antony", 48.753, 2.297),
        ]
        clients = []
        for nom, adr, cp, ville, lat, lng in clients_data:
            c = Client(nom=nom, adresse=adr, code_postal=cp, ville=ville, lat=lat, lng=lng)
            db.add(c); clients.append(c)
        await db.flush()

        # ── Missions (à planifier) ──
        missions_data = [
            ("Bouygues Construction", "15 rue du Faubourg, 93200 Saint-Denis", "livraison", "Haulotte HA20RTJ", 48.936, 2.355),
            ("Vinci Facilities", "8 av. de la République, 75011 Paris", "recuperation", "JLG 460SJ", 48.861, 2.372),
            ("Eiffage Génie Civil", "Zone Industrielle, 77200 Torcy", "livraison", "Manitou MRT 2150", 48.753, 2.649),
            ("GTM Bâtiment", "12 rue Henri Barbusse, 92110 Clichy", "livraison", "Genie Z-60", 48.902, 2.310),
            ("Léon Grosse", "45 bd Gal de Gaulle, 94120 Fontenay", "recuperation", "Skyjack SJ63AJ", 48.775, 2.480),
            ("Colas Île-de-France", "3 allée des Chênes, 91300 Massy", "livraison", "Manitou 180ATJ", 48.726, 2.274),
            ("NGE Construction", "27 rue de la Paix, 78000 Versailles", "livraison", "JLG 800AJ", 48.805, 2.130),
            ("Spie Batignolles", "89 av. Aristide Briand, 92160 Antony", "recuperation", "Haulotte H12SX", 48.753, 2.297),
            ("Eiffage Génie Civil", "Zone Industrielle, 77200 Torcy", "livraison", "Haulotte HA16RTJ", 48.753, 2.649),
            ("GTM Bâtiment", "12 rue Henri Barbusse, 92110 Clichy", "livraison", "Manitou MRT 1745", 48.902, 2.310),
        ]
        for cl, adr, top, mod, lat, lng in missions_data:
            db.add(Mission(client_nom=cl, adresse=adr, type_op=top, machine_modele=mod,
                           machine_id=mby.get(mod), lat=lat, lng=lng,
                           statut="A_PLANIFIER", date_prevue=date(2026, 6, 30)))

        await db.commit()
        print("✅ Seed terminé : 5 users, 1 agence, 10 machines, 5 véhicules, 6 chauffeurs, 8 clients, 10 missions.")


if __name__ == "__main__":
    asyncio.run(seed())
