/* Lecture des données (une fonction use… par route) et écritures (useEcriture) via TanStack Query.
 * Les clés commencent par le module ('budget', 'bourse', 'lectures') : une écriture invalide tout son module. */
import { useEffect } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, apiSilencieux, toast } from './api';
import type {
  BilanLecture, Config, CoursActualisation, DashboardBourse, Dividende, FraisBourse, Gain, Genre, Livre, Mouvement, ObjectifsLecture, Position,
  ResumeAnnee, ResumeGlobal, ResumeJour, ResumeMois, ResumeSemaine, Titre, TransactionBourse, TransactionsMois,
} from './types';

type Module = 'budget' | 'bourse' | 'lectures';

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

/* ---------- Bourse ---------- */
export const useTransactionsBourse = () => lire<TransactionBourse[]>(['bourse', 'transactions'], '/api/bourse/transactions');
export const usePositions = () => lire<Position[]>(['bourse', 'positions'], '/api/bourse/positions');
export const useGains = () => lire<Gain[]>(['bourse', 'gains'], '/api/bourse/gains');
export const useDividendes = () => lire<Dividende[]>(['bourse', 'dividendes'], '/api/bourse/dividendes');
export const useFraisBourse = () => lire<FraisBourse[]>(['bourse', 'frais'], '/api/bourse/frais');
export const useMouvements = () => lire<Mouvement[]>(['bourse', 'mouvements'], '/api/bourse/mouvements');
export const useTitres = () => lire<Titre[]>(['bourse', 'titres'], '/api/bourse/titres');
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
    },
  });
}
