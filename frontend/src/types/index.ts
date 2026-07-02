export type Role = "ADMIN" | "DSI" | "EXPLOITANT" | "CHEF_AGENCE" | "LECTURE";

export interface User { id: number; email: string; full_name: string; role: Role; is_active: boolean; }
export interface TokenPair { access_token: string; refresh_token: string; token_type: string; }

export interface Machine { id: number; modele: string; constructeur: string; famille: string; longueur_m: number; largeur_m: number; hauteur_m: number; poids_kg: number; }
export interface Vehicule { id: number; immatriculation: string; libelle: string; plateau_longueur_m: number; plateau_largeur_m: number; charge_utile_kg: number; conso_l_100km: number; disponible: boolean; }
export interface Chauffeur { id: number; nom: string; telephone: string; permis: string; disponible: boolean; }
export interface Client { id: number; nom: string; adresse: string; code_postal: string; ville: string; lat: number | null; lng: number | null; }
export interface Mission { id: number; client_nom: string; adresse: string; lat: number | null; lng: number | null; type_op: "livraison" | "recuperation"; machine_modele: string; quantite: number; statut: string; date_prevue: string | null; tournee_id: number | null; }
export interface EtapeChrono { heure: string; lieu: string; action: string; machine?: string; duree_min?: number; }
export interface Tournee { id: number; chauffeur_nom: string; vehicule_immat: string; nb_missions: number; km: number; co2_kg: number; taux_remplissage: number; depart: string; statut: string; couleur: string; itineraire: number[][]; explications: string[]; plateau?: PlateauMachine[]; chronologie?: EtapeChrono[]; duree_min?: number; }
export interface Agence { id: number; nom: string; code: string; adresse: string; lat: number; lng: number; }

export interface Kpi { missions: number; tournees: number; km: number; cout_estime: number; carburant_l: number; co2_kg: number; taux_remplissage: number; economies: number; }

export interface ComparisonMetric { label: string; avant: string; apres: string; gain: string; delta_pct: number | null; }
export interface PlateauMachine { machine: string; client?: string; type?: string; longueur: number; largeur: number; poids: number; }
export interface OptimResultTour { index: number; couleur: string; missions: number[]; itineraire: number[][]; km: number; co2_kg: number; taux_remplissage: number; nb_missions: number; explications: string[]; plateau?: PlateauMachine[]; }
export interface OptimizeResult {
  reference: string; statut: string; moteur: string;
  nb_missions: number; nb_tournees: number; nb_tournees_min_theorique: number;
  km_total: number; taux_moyen: number; cout_estime: number; co2_kg: number; duree_calcul_s: number;
  comparaison: ComparisonMetric[]; tournees: OptimResultTour[];
}
