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
/** Total d'une catégorie (dépenses) ou d'une source (revenus) parmi les opérations trouvées */
export type RubriqueRecherche = { type: 'depenses' | 'revenus'; nom: string; nb: number; montant: number };
export type Recherche = {
  resultats: ResultatRecherche[]; nb: number; total_depenses: number; total_revenus: number; par_rubrique: RubriqueRecherche[];
};
/** Période choisie dans la Saisie : [début, fin] AAAA-MM-JJ, bornes incluses */
export type Periode = [string, string];
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
  /** même mois l'an dernier, jusqu'au jour `jour_comparaison_annee` s'il est renseigné */
  depenses_annee_precedente: number;
  revenus_annee_precedente: number;
  depenses_annee_precedente_total: number;
  revenus_annee_precedente_total: number;
  jour_comparaison_annee: number | null;
  depenses_variables: number;
  charges_fixes: boolean;
  projection_fin_mois: number | null;
  /** `an_dernier` : dépensé dans la catégorie le même mois l'an dernier, sur la même durée */
  budget_vs_reel: { cat: string; budget: number; reel: number; pct: number; an_dernier: number }[];
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
export type CibleTitre = { titre: string; cible: number };       // cible : ratio (0,25 = 25 %)

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
  /** Rendement annuel (TRI) pondéré par la date des apports ; null avant 3 mois d'historique */
  rendement_annualise: number | null;
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
  /** Ce que coûtera l'échéance ; `provision` : l'objectif qui la prépare mois après mois */
  montant: number | null; objectif_id: number | null; provision: Provision | null;
};
export type Provision = { objectif_id: number; verse: number; cible: number; reste: number; par_mois: number | null; archive: boolean };

/* ---------- Rappels et résumé hebdomadaire ---------- */
export type Canal = 'telegram' | 'email';
/** Envoi automatique réglable canal par canal : note du jour (avec le message du matin) et résumés */
export type Envoi = 'note' | 'semaine' | 'mois' | 'annee';
/** `envois` : canaux choisis pour chaque envoi (configurés sur le serveur ou non) */
/** Un appel de la tâche planifiée : `detail` = ce qui est parti (et sur quels canaux) ou l'erreur */
export type PassageCron = { le: string; etat: 'ok' | 'deja_fait' | 'aucun_canal' | 'erreur'; detail: string };
/** `passages` : derniers appels de la tâche planifiée, du plus récent au plus ancien */
export type EtatRappels = {
  canaux: Canal[]; cron: boolean; envois: Record<Envoi, Canal[]>; passages: PassageCron[];
  /** dernier appel de la tâche planifiée qui n'a pas échoué (null : aucun dans le journal) */
  dernier_succes: string | null;
};
/** `html` : l'e-mail tel qu'il sera envoyé ; `resume` : sa version texte brut */
export type ApercuRappels = { rappels: string; sujet: string; resume: string; html: string };

/* ---------- Objectifs d'épargne par projet ---------- */
/** `montant` négatif : argent repris à l'objectif */
export type Versement = { id: number; date_operation: string; montant: number; libelle: string };
/** `par_mois` : à mettre de côté chaque mois pour tenir la date limite (null sans date, atteint ou dépassée) */
export type Projet = {
  id: number; nom: string; cible: number; date_limite: string | null; note: string; archive: boolean;
  verse: number; reste: number; progression: number; atteint: boolean;
  mois_restants: number | null; par_mois: number | null; en_retard: boolean; versements: Versement[];
  /** Suivi par un tag : dépenses portant le tag depuis `tag_depuis`, prises sur l'argent mis de côté.
   *  `reserve` = encore réservé (sans tag : `verse`), `depassement` = dépensé au-delà de l'enveloppe */
  tag: string | null; tag_depuis: string | null; depense: number; reserve: number; depassement: number;
  operations: OperationTaggee[];
  /** Objectif qui provisionne une échéance (Suivi → Échéances) */
  echeance_id: number | null;
};
/** Dépense (ou remboursement, en revenu) portant le tag d'un objectif */
export type OperationTaggee = { type: 'depense' | 'revenu'; id: number; date: string; nom: string; description: string; montant: number };

/* ---------- Patrimoine ---------- */
/** Patrimoine noté un jour donné (courbe) */
/** `estime` : fin de mois reconstituée après coup (Évolution → « Reconstituer les mois passés ») */
export type PointPatrimoine = {
  date: string; estime: boolean; total: number; liquidites: number; bourse: number; autres_actifs: number; creances: number; dettes: number;
};
/** Cours d'un titre détenu à une date passée : `estime` est celui utilisé sans saisie (source : dernière
 *  transaction ou cours actuel, à `source_date`), `saisi` celui relevé à la main pour cette date */
export type CoursPasse = {
  titre: string; quantite: number; saisi: number | null; estime: number | null;
  source: 'transaction' | 'historique' | 'actuel' | 'saisi' | null; source_date: string | null;
};
export type Reconstitution = { points: number; debut: string | null; fin: string | null };
/** `verse` : argent sorti de l'épargne pour cet actif sans être saisi en dépense */
/** Versement (montant positif) ou retrait (négatif) d'un actif */
export type MouvementActif = { id: number; date_operation: string; montant: number; libelle: string };
export type Actif = {
  id: number; nom: string; type: string; valeur: number; verse: number; zakat: boolean; maj_le: string; note: string;
  mouvements: MouvementActif[];
};
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
  /** Dernier pointage du solde (null : jamais) ; `ecart` = réel − calculé */
  pointage: { date: string; jours: number; ecart: number; regle: 'depense' | 'revenu' | null; a_refaire: boolean } | null;
};

/** Pointage du solde : `solde_calcule` = liquidités calculées du jour ; `ecart` = réel − calculé (négatif : il manque de l'argent) */
export type Rapprochement = {
  id: number; date: string; solde_reel: number; solde_calcule: number; ecart: number;
  comptes: { nom: string; montant: number }[]; regle: 'depense' | 'revenu' | null; note: string;
};
export type Rapprochements = {
  solde_calcule: number; historique: Rapprochement[]; jours_sans_depense: string[]; depuis: string; a_refaire_jours: number;
};

/** Dépense inhabituelle (accueil) ; `cle` sert à l'ignorer */
export type Alerte = {
  cle: string; type: 'categorie' | 'hausse' | 'doublon'; categorie: string; titre: string; detail: string; montant: number; date?: string;
};

/** Saisie par Telegram : `actif` = webhook déclaré à l'adresse de l'application */
export type EtatTelegram = { configure: boolean; actif: boolean; adresse: string | null; erreur: string | null };
/** Liberté financière. Les champs calculés manquent tant qu'aucun mois terminé n'a de dépenses ;
 *  `annees_restantes` / `date_atteinte` null si l'objectif n'est pas atteint en 100 ans. */
export type Liberte = {
  taux_retrait: number; rendement: number; patrimoine: number; exclus: number; nb_mois_base: number;
  depense_annuelle?: number; epargne_annuelle?: number; cible?: number; progression?: number; annees_couvertes?: number;
  annees_restantes?: number | null; date_atteinte?: string | null; economie_simulee?: number; annees_gagnees?: number | null;
};

/* ---------- Opérations récurrentes ---------- */
export type TypeOperation = 'depense' | 'revenu';
/** `nom` : catégorie (dépense) ou source (revenu, vide : sans source) ; `debut` et `dernier_mois` : AAAA-MM */
export type Recurrence = {
  id: number; type: TypeOperation; nom: string; categorie: string | null; source: string | null; description: string;
  montant: number; jour: number; tags: string[]; auto: boolean; actif: boolean; debut: string; dernier_mois: string | null;
  prochain_mois: string; prochaine_date: string; en_attente: number;
};
/** Opération d'une récurrence encore à ajouter (jusqu'au mois en cours) ; `a_venir` : sa date n'est pas encore arrivée */
export type RecurrenceAGenerer = {
  id: number; type: TypeOperation; nom: string; description: string; montant: number; auto: boolean; mois: string; date: string; a_venir: boolean;
};
export type SuggestionRecurrence = { type: TypeOperation; nom: string; description: string; montant: number; jour: number; tags: string[]; moyenne: number };
export type Generation = { generees: { id: number; montant: number; date: string }[]; ignorees: number };

/* ---------- Prévisions de trésorerie ---------- */
/** `base` : d'où vient le montant attendu (récurrence, budget d'une catégorie fixe, moyenne ou médiane du passé, déjà saisi) */
export type LignePrevision = { nom: string; montant: number; base: 'recurrence' | 'budget' | 'moyenne' | 'saisi' };
export type MoisPrevision = {
  mois: string; revenus: number; depenses: number; echeances: number; dettes: number;
  solde: number; bas: number; haut: number; reserve: number; libre: number;
  detail: {
    revenus: LignePrevision[]; depenses: LignePrevision[];
    echeances: { titre: string; date: string; montant: number }[];
    dettes: { personne: string; date: string; montant: number; en_retard: boolean }[];
  };
};
export type AlertePrevision = { type: 'plancher' | 'reserve' | 'objectifs' | 'rythme'; mois: string; titre: string; detail: string };
export type Previsions = {
  /** depart = depart_liquidites (compte courant calculé) + depart_epargne (actifs « Compte épargne ») */
  date: string; depart: number; depart_liquidites: number; depart_epargne: number; plancher: number; nb_mois_historique: number; mois: MoisPrevision[];
  point_bas: { mois: string; solde: number }; epargne_prevue: number; rythme_objectifs: number; alertes: AlertePrevision[];
};

/* ---------- Historique des cours ---------- */
export type HistoriquePortefeuille = { titres: string[]; points: { date: string; valeur: number; cout: number }[] };
export type HistoriqueTitre = { titre: string; points: { date: string; cours: number; manuel: boolean }[] };
/** Jours où la Bourse est fermée : `variables` saisis (fêtes religieuses), `fixes` connus d'avance */
export type JoursFeries = { variables: { date: string; libelle: string }[]; fixes: { mois: number; jour: number; libelle: string }[] };
/** Titre détenu au cours périmé : `jours` de bourse sans clôture notée (automatique) ou depuis la saisie (manuel) */
export type CoursEnRetard = { titre: string; manuel: boolean; depuis: string | null; jours: number };

/* ---------- Indices de référence ---------- */
export type IndiceSuivi = {
  code: string; nom: string; dividendes: boolean; nb: number; nb_import: number; debut: string | null; fin: string | null; derniere: number | null;
};
export type Indices = { defaut: string; premier_mouvement: string | null; indices: IndiceSuivi[] };
/** `etat` : ok, vide (aucune valeur), incomplet (un apport précède l'historique : `manque_avant`), sans_apport */
/** « compte » : apports placés dans l'indice, contre titres + espèces ; « titres » : achats placés dans l'indice, contre la valeur de marché */
export type ModeComparaison = 'compte' | 'titres';
export type Comparaison = {
  indice: string; nom: string; dividendes: boolean; mode: ModeComparaison; etat: 'ok' | 'vide' | 'incomplet' | 'sans_apport';
  manque_avant: string | null; date_valeur: string | null; apports_nets: number; debut_cours: string | null;
  toi: { valeur: number; rendement: number | null }; reference: { valeur: number; rendement: number | null } | null;
  ecart: number | null; points: { date: string; indice: number; toi: number }[];
};
/** Cours connus d'un titre déjà acheté (clôtures du soir et cours importés), et son premier achat à couvrir */
export type CouvertureTitre = {
  titre: string; premier_achat: string; detenu: boolean; nb: number; nb_import: number; debut: string | null; fin: string | null;
};
