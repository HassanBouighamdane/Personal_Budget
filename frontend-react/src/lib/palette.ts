/* Couleurs des graphiques et des montants */

/** Palette catégorielle (donuts, barres par catégorie) */
export const PALETTE = ['#6366f1', '#f59e0b', '#10b981', '#f43f5e', '#0ea5e9', '#a855f7', '#84cc16', '#f97316'];
const GRIS_AUTRES = '#94a3b8';

/** Couleurs des séries Chart.js (valeurs hexadécimales : le canvas ne lit pas les variables CSS) */
export const C = { dep: '#f43f5e', rev: '#3b82f6', ep: '#10b981', budget: '#94a3b8' };

/** Couleurs des textes (variables CSS de global.css) */
export const T = { dep: 'var(--c-dep)', rev: 'var(--c-rev)', ep: 'var(--c-ep)', neg: 'var(--c-neg)', warn: 'var(--c-warn)' };

/** Vert si positif ou nul, rouge sinon */
export const signe = (v: number) => (v >= 0 ? T.ep : T.neg);

/** Garde les `max` plus grandes parts et regroupe le reste dans « Autres » */
export function regrouperAutres(labels: string[], valeurs: number[], max = 7) {
  if (labels.length <= max + 1) return { labels, valeurs, couleurs: PALETTE.slice(0, labels.length) };
  const paires = labels.map((l, i) => [l, valeurs[i]] as const).sort((a, b) => b[1] - a[1]);
  const gardees = paires.slice(0, max);
  const reste = paires.slice(max).reduce((s, [, v]) => s + v, 0);
  return {
    labels: [...gardees.map(p => p[0]), 'Autres'],
    valeurs: [...gardees.map(p => p[1]), reste],
    couleurs: [...PALETTE.slice(0, max), GRIS_AUTRES],
  };
}
