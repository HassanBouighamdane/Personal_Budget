/* Types des réponses de l'API (dates en chaîne AAAA-MM-JJ) */

/* ---------- Budget ---------- */
export type Categorie = { id: number; nom: string; budget: number };
export type Source = { id: number; nom: string };
export type Config = { categories: Categorie[]; sources: Source[]; objectif_epargne: number };

export type Depense = { id: number; date: string; categorie: string; description: string; montant: number };
export type Revenu = { id: number; date: string; source: string; montant: number };
export type TransactionsMois = { depenses: Depense[]; revenus: Revenu[] };

type PartCategorie = { cat: string; montant: number };
type TopDepense = { date: string; categorie: string; description: string; montant: number };

export type ResumeJour = {
  date: string;
  total_depenses: number;
  total_revenus: number;
  depenses_veille: number;
  nb_transactions: number;
  moyenne_jour_mois: number;
  budget_jour: number;
  donut: PartCategorie[];
  depenses: Omit<Depense, 'date'>[];
  revenus: Omit<Revenu, 'date'>[];
};

export type ResumeSemaine = {
  lundi: string;
  dimanche: string;
  total_depenses: number;
  total_revenus: number;
  epargne: number;
  depenses_semaine_precedente: number;
  revenus_semaine_precedente: number;
  budget_hebdo: number;
  reste_budget_hebdo: number;
  par_jour: { date: string; dep: number; rev: number }[];
  donut: PartCategorie[];
  top: TopDepense[];
};

export type ResumeMois = {
  mois: string;
  nb_jours: number;
  total_depenses: number;
  total_revenus: number;
  epargne: number;
  taux_epargne: number;
  objectif_epargne: number;
  budget_total: number;
  reste_budget: number;
  depenses_mois_precedent: number;
  revenus_mois_precedent: number;
  projection_fin_mois: number | null;
  budget_vs_reel: { cat: string; budget: number; reel: number; pct: number }[];
  cumul_quotidien: number[];
  donut: PartCategorie[];
  evolution: { m: string; dep: number; rev: number }[];
  top: TopDepense[];
};

type MoisAnnee = { m: number; dep: number; rev: number; ep: number };
export type ResumeAnnee = {
  annee: number;
  total_depenses: number;
  total_revenus: number;
  epargne: number;
  taux_epargne: number;
  moyenne_dep_mois: number;
  nb_mois_actifs: number;
  nb_mois_objectif: number;
  objectif_epargne: number;
  meilleur_mois: MoisAnnee | null;
  pire_mois: MoisAnnee | null;
  par_mois: MoisAnnee[];
  epargne_cumulee: number[];
  categories: { cat: string; total: number; budget_annuel: number; pct: number }[];
  grille: Record<string, number[]>;
};

type MoisGlobal = { m: string; dep: number; rev: number; ep: number };
export type ResumeGlobal = {
  premier_mois: string | null;
  dernier_mois: string | null;
  total_depenses: number;
  total_revenus: number;
  epargne: number;
  taux_epargne: number;
  nb_mois_actifs: number;
  moyenne_dep_mois: number;
  moyenne_rev_mois: number;
  nb_mois_objectif: number;
  objectif_epargne: number;
  meilleur_mois: MoisGlobal | null;
  pire_mois: MoisGlobal | null;
  par_mois: MoisGlobal[];
  epargne_cumulee: number[];
  par_annee: { annee: number; dep: number; rev: number; ep: number; taux_epargne: number }[];
  donut: PartCategorie[];
  top: TopDepense[];
};

/* ---------- Bourse ---------- */
export type Titre = { id: number; code: string; nom: string; secteur: string };

export type TransactionBourse = {
  id: number;
  date_operation: string;
  titre: string;
  isin: string | null;
  type_instrument: string;
  type_operation: 'Achat' | 'Vente';
  quantite: number;
  cours_unitaire: number;
  montant_brut: number;
  autres_frais: number;
  total_frais: number;
  tpcvm: number;
  montant_net: number;
};

export type Position = {
  titre: string;
  secteur: string;
  quantite_achetee: number;
  quantite_vendue: number;
  quantite_detenue: number;
  pru: number;
  cours_actuel: number;
  valeur_comptable: number;
  valeur_marche: number;
  plus_value_latente: number;
  performance_latente: number;
};

export type Gain = {
  id: number;
  date_operation: string;
  titre: string;
  type_instrument: string;
  quantite: number;
  cours_vente: number;
  pru: number;
  montant_net: number;
  gain_brut: number;
  taux_tpcvm: number;
  tpcvm: number;
  gain_net: number;
};

export type Dividende = { id: number; date_operation: string; titre: string; montant: number };
export type FraisBourse = { id: number; date_operation: string; libelle: string; montant: number };
export type Mouvement = { id: number; date_operation: string; type_mouvement: 'Apport' | 'Retrait'; montant: number; libelle: string };

export type DashboardBourse = {
  cout_acquisition: number;
  valeur_marche: number;
  plus_value_latente: number;
  performance_latente: number;
  gains_bruts_realises: number;
  tpcvm_total: number;
  gains_nets_realises: number;
  dividendes_nets: number;
  frais_transactions_totaux: number;
  frais_compte_totaux: number;
  resultat_net_periode: number;
  apports_periode: number;
  retraits_periode: number;
  especes_disponibles: number;
  apports_nets: number;
  patrimoine_total: number;
  performance_globale: number;
  performance_globale_pct: number;
};

/* ---------- Lectures ---------- */
export type Livre = {
  id: number;
  titre: string;
  auteur: string;
  genre: string;
  date_debut: string | null;
  date_fin: string;
  pages: number | null;
  note: number | null;
  commentaire: string;
};

export type Genre = { id: number; nom: string };
export type ObjectifsLecture = { annuel: number; mensuel: number };

export type BilanLecture = {
  annee: number;
  est_annee_courante: boolean;
  nb_livres: number;
  nb_pages: number;
  pages_moyennes: number;
  note_moyenne: number | null;
  duree_moyenne_jours: number | null;
  nb_livres_annee_precedente: number;
  objectif_annuel: number;
  objectif_mensuel: number;
  attendu_a_date: number;
  nb_mois_ecoules: number;
  nb_mois_objectif: number;
  livres_mois_courant: number | null;
  par_mois: { m: number; livres: number; pages: number }[];
  genres: { genre: string; livres: number; pages: number }[];
  auteurs: { auteur: string; livres: number }[];
  mieux_note: Livre | null;
  plus_long: Livre | null;
  plus_court: Livre | null;
  historique: { annee: number; livres: number; pages: number }[];
  livres: Livre[];
};
