/* Lecture des données (une fonction use… par route) et écritures (useEcriture) via TanStack Query.
 * Les clés commencent par le module ('budget', 'bourse', 'lectures', 'carnet') : une écriture invalide tout son module. */
import { useEffect } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, apiSilencieux, toast } from './api';
import type {
  ALire, ApercuRappels, BilanLecture, CalendrierDividendes, NoteDuJour, Patrimoine, PretLivre, SerieLecture, BudgetHistorique, CibleSecteur, Config, CoursActualisation, DashboardBourse, Dette, Dividende, Echeance, EtatRappels, Fiscalite, FraisBourse, Gain, Genre,
  Livre, Mouvement, NoteLecture, ObjectifsLecture, Position, Recherche, ResumeAnnee, ResumeGlobal, ResumeJour, ResumeMois, ResumeSemaine, ResumeTag,
  Suggestion, Titre, TransactionBourse, TransactionsMois,
} from './types';

type Module = 'budget' | 'bourse' | 'lectures' | 'carnet' | 'patrimoine';

// placeholderData : en changeant de période, l'ancien contenu reste affiché pendant le chargement
function lire<T>(cle: unknown[], path: string) {
  return useQuery({ queryKey: cle, queryFn: () => api<T>(path), placeholderData: keepPreviousData });
}

/* ---------- Budget ---------- */
export const useConfig = () => lire<Config>(['budget', 'config'], '/api/categories');
export const useTransactionsMois = (mois: string) => lire<TransactionsMois>(['budget', 'transactions', mois], '/api/transactions?mois=' + mois);
export const useResumeMois = (mois: string) => lire<ResumeMois>(['budget', 'resume', mois], '/api/resume?mois=' + mois);
export const useResumeJour = (date: string) => lire<ResumeJour>(['budget', 'jour', date], '/api/resume_jour?date=' + date);
export const useResumeSemaine = (date: string) => lire<ResumeSemaine>(['budget', 'semaine', date], '/api/resume_semaine?date=' + date);
export const useResumeAnnee = (annee: number) => lire<ResumeAnnee>(['budget', 'annee', annee], '/api/resume_annuel?annee=' + annee);
export const useResumeGlobal = () => lire<ResumeGlobal>(['budget', 'global'], '/api/resume_global');
export const useRecherche = (q: string, decalage: number) => useQuery({
  queryKey: ['budget', 'recherche', q, decalage],
  queryFn: () => api<Recherche>(`/api/recherche?q=${encodeURIComponent(q)}&limite=50&decalage=${decalage}`),
  placeholderData: keepPreviousData,
  enabled: q.trim().length > 0,
});
/** Dernières descriptions d'une catégorie / source (aucune requête sans nom choisi) */
export const useSuggestions = (type: 'depenses' | 'revenus', nom: string | null) => useQuery({
  queryKey: ['budget', 'suggestions', type, nom],
  queryFn: () => apiSilencieux<Suggestion[]>(`/api/suggestions?type=${type}&nom=${encodeURIComponent(nom ?? '')}`),
  enabled: !!nom,
});
export const useTags = () => lire<ResumeTag[]>(['budget', 'tags'], '/api/tags');
export const useHistoriqueBudget = (cid: number) => lire<BudgetHistorique[]>(['budget', 'historique', cid], `/api/categories/${cid}/historique`);

/* ---------- Bourse ---------- */
export const useTransactionsBourse = () => lire<TransactionBourse[]>(['bourse', 'transactions'], '/api/bourse/transactions');
export const usePositions = () => lire<Position[]>(['bourse', 'positions'], '/api/bourse/positions');
export const useGains = () => lire<Gain[]>(['bourse', 'gains'], '/api/bourse/gains');
export const useDividendes = () => lire<Dividende[]>(['bourse', 'dividendes'], '/api/bourse/dividendes');
export const useFraisBourse = () => lire<FraisBourse[]>(['bourse', 'frais'], '/api/bourse/frais');
export const useMouvements = () => lire<Mouvement[]>(['bourse', 'mouvements'], '/api/bourse/mouvements');
export const useTitres = () => lire<Titre[]>(['bourse', 'titres'], '/api/bourse/titres');
export const useCalendrierDividendes = () => lire<CalendrierDividendes>(['bourse', 'calendrier'], '/api/bourse/dividendes/calendrier');
export const useCibles = () => lire<CibleSecteur[]>(['bourse', 'cibles'], '/api/bourse/cibles');
export const useFiscalite = (annee: number) => lire<Fiscalite>(['bourse', 'fiscalite', annee], '/api/bourse/fiscalite?annee=' + annee);
export const useDashboardBourse = (requete: string) =>
  lire<DashboardBourse>(['bourse', 'dashboard', requete], '/api/bourse/dashboard' + (requete ? '?' + requete : ''));

/** KPI Bourse du dashboard Budget : n'affiche jamais d'erreur (un problème Bourse ne casse pas le Budget) */
export const useResumeBourseSilencieux = (requete: string) => useQuery({
  queryKey: ['bourse', 'resume-silencieux', requete],
  queryFn: () => apiSilencieux<DashboardBourse>('/api/bourse/dashboard?' + requete),
  placeholderData: keepPreviousData,
});

/** À l'ouverture d'un écran : récupère les cours s'ils datent (le serveur limite à une fois par
 *  quart d'heure). Jamais d'erreur affichée : à défaut, les derniers cours connus restent. */
export function useCoursAuto() {
  const qc = useQueryClient();
  useEffect(() => {
    apiSilencieux<CoursActualisation>('/api/bourse/cours/actualiser', 'POST')
      .then(r => { if (r?.etat === 'maj') qc.invalidateQueries({ queryKey: ['bourse'] }); });
  }, [qc]);
}

/** Bouton « Actualiser les cours » (titre = null) ou remise d'un cours manuel en automatique */
export function useActualiserCours() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (titre: string | null) => titre
      ? api<CoursActualisation>(`/api/bourse/prix/${encodeURIComponent(titre)}/auto`, { method: 'PUT' })
      : api<CoursActualisation>('/api/bourse/cours/actualiser?force=true', { method: 'POST' }),
    onSuccess: r => {
      const introuvables = r.introuvables.length ? ' · introuvables : ' + r.introuvables.join(', ') : '';
      toast(r.message + introuvables, r.etat !== 'erreur');
      qc.invalidateQueries({ queryKey: ['bourse'] });
    },
  });
}

/* ---------- Lectures ---------- */
export const useLivres = (annee: number) => lire<Livre[]>(['lectures', 'livres', annee], '/api/lectures/livres?annee=' + annee);
export const useAuteurs = () => lire<string[]>(['lectures', 'auteurs'], '/api/lectures/auteurs');
export const useGenres = () => lire<Genre[]>(['lectures', 'genres'], '/api/lectures/genres');
export const useObjectifsLecture = () => lire<ObjectifsLecture>(['lectures', 'objectifs'], '/api/lectures/objectifs');
export const useBilanLecture = (annee: number) => lire<BilanLecture>(['lectures', 'bilan', annee], '/api/lectures/bilan?annee=' + annee);
export const useALire = () => lire<ALire[]>(['lectures', 'a_lire'], '/api/lectures/a_lire');
export const useSerieLecture = () => lire<SerieLecture>(['lectures', 'serie'], '/api/lectures/serie');
export const usePretsLivres = () => lire<PretLivre[]>(['lectures', 'prets'], '/api/lectures/prets');
export const useTitresLivres = () => lire<string[]>(['lectures', 'titres'], '/api/lectures/titres');
/** Note ou citation du jour ; `decalage` en fait défiler d'autres. Jamais d'erreur affichée. */
export const useNoteDuJour = (decalage: number) => useQuery({
  queryKey: ['lectures', 'note_du_jour', decalage],
  queryFn: () => apiSilencieux<NoteDuJour>('/api/lectures/note_du_jour?decalage=' + decalage),
  placeholderData: keepPreviousData,
});
/** Notes d'un livre terminé (`livre_id=…`) ou à lire (`a_lire_id=…`) */
export const useNotes = (filtre: string) => lire<NoteLecture[]>(['lectures', 'notes', filtre], '/api/lectures/notes?' + filtre);

/* ---------- Carnet ---------- */
export const useDettes = () => lire<Dette[]>(['carnet', 'dettes'], '/api/carnet/dettes');
export const useEcheances = () => lire<Echeance[]>(['carnet', 'echeances'], '/api/carnet/echeances');

/* ---------- Patrimoine (dépend de tous les modules : rechargé après chaque écriture) ---------- */
export const usePatrimoine = () => lire<Patrimoine>(['patrimoine'], '/api/patrimoine');
/** Pour le dashboard Budget : n'affiche jamais d'erreur */
export const usePatrimoineSilencieux = () => useQuery({
  queryKey: ['patrimoine', 'silencieux'], queryFn: () => apiSilencieux<Patrimoine>('/api/patrimoine'), placeholderData: keepPreviousData,
});

/* ---------- Rappels et résumé hebdomadaire ---------- */
export const useEtatRappels = () => lire<EtatRappels>(['rappels', 'etat'], '/api/rappels/etat');
/** Jamais gardé en cache : l'aperçu reflète les données du moment où on l'ouvre */
export const useApercuRappels = (periode: 'semaine' | 'mois') => useQuery({
  queryKey: ['rappels', 'apercu', periode], queryFn: () => api<ApercuRappels>('/api/rappels/apercu?periode=' + periode), gcTime: 0,
});

/* ---------- Écritures ---------- */
type Ecriture = { path: string; method: string; body?: unknown; succes?: string };

/** Envoie la requête, notifie le succès puis recharge tout le module concerné */
export function useEcriture(module: Module) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (e: Ecriture) => api(e.path, { method: e.method, body: e.body }),
    onSuccess: (_, e) => {
      if (e.succes) toast(e.succes);
      qc.invalidateQueries({ queryKey: [module] });
      if (module !== 'patrimoine') qc.invalidateQueries({ queryKey: ['patrimoine'] });
    },
  });
}
