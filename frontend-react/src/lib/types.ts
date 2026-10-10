/* Types des réponses de l'API (dates en chaîne AAAA-MM-JJ) */

/* ---------- Budget ---------- */
/** `fixe` : charge fixe (loyer, factures), hors budget journalier/hebdo */
export type Categorie = { id: number; nom: string; budget: number; fixe: boolean };
/** `travail` : revenu du travail (salaire, prime, freelance), sert au taux horaire */
export type Source = { id: number; nom: string; travail: boolean };
/** Prix en heures de travail : `taux_horaire` null sans revenu du travail sur les 12 derniers mois terminés */
export type Travail = { heures_mois: number; revenu_mensuel: number; nb_mois: number; taux_horaire: number | null };
export type Config = { categories: Categorie[]; sources: Source[]; objectif_epargne: number; travail: Travail };

export type Depense = { id: number; date: string; categorie: string; description: string; montant: number; tags: string[] };
export type Revenu = { id: number; date: string; source: string; description: string; montant: number; tags: string[] };
export type TransactionsMois = { depenses: Depense[]; revenus: Revenu[] };

/** Ligne de recherche : `nom` = catégorie (dépense) ou source (revenu) */
export type ResultatRecherche = {
  type: 'depenses' | 'revenus'; id: number; date: string; nom: string; description: string; montant: number; tags: string[];
};
export type Recherche = { resultats: ResultatRecherche[]; nb: number; total_depenses: number; total_revenus: number };
export type Suggestion = { description: string; montant: number };
export type ResumeTag = { tag: string; nb: number; depenses: number; revenus: number; premier: string; dernier: string };
/** Budget d'une catégorie à partir d'un mois (AAAA-MM ; 1900-01 = depuis toujours) */
export type BudgetHistorique = { mois_debut: string; budget: number; fixe: boolean };
export type LigneImport = { type: 'depense' | 'revenu'; date: string; nom: string; description: string; montant: number; tags: string[] };
export type ResultatImport = {
  statuts: { statut: 'ajoutee' | 'doublon' | 'erreur'; message: string }[];
  nb_ajoutees: number; nb_doublons: number; nb_erreurs: number; simulation: boolean;
};

type PartCategorie = { cat: string; montant: number };
type TopDepense = { date: string; categorie: string; description: string; montant: number };

export type ResumeJour = {
  date: string;
  total_depenses: number;
  total_revenus: number;
  depenses_variables: number;
  charges_fixes: boolean;
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
  /** semaine précédente jusqu'au même jour si `comparaison_partielle` */
  depenses_semaine_precedente: number;
  revenus_semaine_precedente: number;
  depenses_semaine_precedente_totale: number;
  comparaison_partielle: boolean;
  depenses_variables: number;
  charges_fixes: boolean;
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
  /** mois précédent jusqu'au jour `jour_comparaison` s'il est renseigné */
  depenses_mois_precedent: number;
  revenus_mois_precedent: number;
  depenses_mois_precedent_total: number;
  revenus_mois_precedent_total: number;
  jour_comparaison: number | null;
  depenses_variables: number;
  charges_fixes: boolean;
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
  /** statistiques sur les mois terminés uniquement */
  moyenne_dep_mois: number;
  nb_mois_actifs: number;
  nb_mois_objectif: number;
  mois_en_cours: number | null;
  objectif_epargne: number;
  meilleur_mois: MoisAnnee | null;
  pire_mois: MoisAnnee | null;
  par_mois: MoisAnnee[];
  epargne_cumulee: number[];
  categories: { cat: string; total: number; budget_annuel: number; budget_a_date: number; pct: number }[];
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
export type Titre = { id: number; code: string; nom: string; secteur: string; isin: string | null };

/** Résultat d'une récupération des cours automatiques */
export type CoursActualisation = { etat: 'maj' | 'recent' | 'rien' | 'erreur'; nb_maj: number; introuvables: string[]; message: string };

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
  /** Pourquoi j'ai acheté ou vendu */
  note: string;
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
  isin: string | null;
  cours_manuel: boolean;        // saisi à la main : verrouillé jusqu'à remise en automatique
  cours_maj_le: string | null;
  dividendes_12m: number;
  rendement_cout: number;       // ratio
  rendement_marche: number;     // ratio
};

export type CibleSecteur = { secteur: string; cible: number };   // cible : ratio (0,25 = 25 %)

export type Fiscalite = {
  annee: number;
  nb_ventes: number;
  montant_cessions: number;
  plus_values_brutes: number;
  moins_values_brutes: number;
  resultat_cessions: number;
  tpcvm_retenue: number;
  taux_tpcvm: number;
  tpcvm_theorique: number;
  ecart_tpcvm: number;
  dividendes_nets: number;
  frais_compte: number;
  par_titre: { titre: string; nb_ventes: number; cessions: number; gain_brut: number; tpcvm: number; dividendes: number }[];
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
/** Dividendes attendus sur 12 mois : dernier dividende par action × quantité détenue aujourd'hui */
export type CalendrierDividendes = {
  total: number;
  lignes: { titre: string; nom: string; date_prevue: string; montant_prevu: number; par_action: number; quantite: number;
            dernier_montant: number; derniere_date: string }[];
};
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
  couverture: string;
  nb_notes: number;
};

/** Livre à lire ; `date_debut` renseignée = en cours de lecture */
export type ALire = {
  id: number; titre: string; auteur: string; genre: string; pages: number | null; couverture: string;
  commentaire: string; date_debut: string | null; nb_notes: number;
  /** Suivi de la lecture en cours : null tant qu'aucune page n'est notée */
  page_actuelle: number | null; derniere_lecture: string | null; pages_par_jour: number | null; fin_estimee: string | null;
};
/** Jours de lecture consécutifs (la série tient encore si on a lu hier) */
export type SerieLecture = { serie: number; record: number; lu_aujourdhui: boolean };
export type NoteDuJour = { id: number; type: 'note' | 'citation'; texte: string; page: number | null; titre: string; auteur: string };
/** Livre prêté ; `date_retour` renseignée = rendu ; `jours` : durée du prêt */
export type PretLivre = { id: number; titre: string; personne: string; date_pret: string; date_retour: string | null; note: string; jours: number };
export type NoteLecture = { id: number; livre_id: number | null; a_lire_id: number | null; type: 'note' | 'citation'; texte: string; page: number | null };

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

/* ---------- Carnet ---------- */
export type Remboursement = { id: number; date_operation: string; montant: number; libelle: string };
/** `pret` : j'ai prêté (on me doit) ; `emprunt` : j'ai emprunté (je dois). `reste` = montant − remboursements */
export type Dette = {
  id: number; sens: 'pret' | 'emprunt'; personne: string; montant: number; date_operation: string; echeance: string | null;
  libelle: string; rembourse: number; reste: number; remboursements: Remboursement[];
};
/** `jours_restants` négatif = en retard ; `a_rappeler` : dans la fenêtre de rappel ou en retard */
export type Echeance = {
  id: number; titre: string; categorie: string; date_echeance: string; rappel_jours: number; recurrence_mois: number | null;
  note: string; jours_restants: number; a_rappeler: boolean;
};

/* ---------- Rappels et résumé hebdomadaire ---------- */
export type EtatRappels = { canaux: ('telegram' | 'email')[]; cron: boolean };
/** `html` : l'e-mail tel qu'il sera envoyé ; `resume` : sa version texte brut */
export type ApercuRappels = { rappels: string; sujet: string; resume: string; html: string };

/* ---------- Patrimoine ---------- */
/** `verse` : argent sorti de l'épargne pour cet actif sans être saisi en dépense */
export type Actif = { id: number; nom: string; type: string; valeur: number; verse: number; zakat: boolean; maj_le: string; note: string };
export type Patrimoine = {
  solde_depart: number; epargne_cumulee: number;
  liquidites: number; bourse: number; autres_actifs: number; creances: number; dettes: number; total: number;
  actifs: Actif[];
  types_actifs: { type: string; zakat: boolean }[];
  /** `mois_couverts` null tant qu'aucun mois terminé n'a de dépenses */
  reserve: { disponible: number; depense_moyenne: number; nb_mois_base: number; mois_couverts: number | null };
  zakat: {
    prix_or_gramme: number; nisab: number | null; assiette: number;
    detail: { liquidites: number; bourse: number; actifs: number; creances: number; dettes: number };
    atteint: boolean; montant: number; debut_hawl: string | null; echeance: string | null; jours_restants: number | null;
  };
  liberte: Liberte;
};
/** Liberté financière. Les champs calculés manquent tant qu'aucun mois terminé n'a de dépenses ;
 *  `annees_restantes` / `date_atteinte` null si l'objectif n'est pas atteint en 100 ans. */
export type Liberte = {
  taux_retrait: number; rendement: number; patrimoine: number; exclus: number; nb_mois_base: number;
  depense_annuelle?: number; epargne_annuelle?: number; cible?: number; progression?: number; annees_couvertes?: number;
  annees_restantes?: number | null; date_atteinte?: string | null; economie_simulee?: number; annees_gagnees?: number | null;
};
