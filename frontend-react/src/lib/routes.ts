/* Navigation dans l'URL (#/dashboard/mois/2026-10) : un rechargement garde la page, une vue peut
 * être mise en favori et le bouton « Retour » du navigateur revient à l'onglet ou à la vue précédente.
 * Chaque module expose `chemin()` (son état → segments) et `appliquer(segments)` (l'inverse). */

/** Segments de l'adresse actuelle : « #/bourse/dashboard/annee/2026 » → ['bourse', 'dashboard', 'annee', '2026'] */
export function lireChemin(): string[] {
  return window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(s => {
    try { return decodeURIComponent(s); } catch { return s; }
  });
}

/** Écrit l'adresse ; `nouvellePage` ajoute une entrée à l'historique (changement d'onglet ou de vue),
 *  sinon elle est remplacée (changement de période : « Retour » ne repasse pas par chaque mois). */
export function ecrireChemin(segments: string[], nouvellePage: boolean) {
  const hash = '#/' + segments.map(encodeURIComponent).join('/');
  if (hash === window.location.hash) return;
  if (nouvellePage) window.history.pushState(null, '', hash);
  else window.history.replaceState(null, '', hash);
}

export const estMois = (s?: string) => !!s && /^\d{4}-(0[1-9]|1[0-2])$/.test(s);
export const estDate = (s?: string) => !!s && /^\d{4}-\d{2}-\d{2}$/.test(s) && !isNaN(Date.parse(s));
export const estAnnee = (s?: string) => !!s && /^\d{4}$/.test(s);

/** La première valeur de `valeurs` égale à `s`, sinon `defaut` */
export function parmi<T extends string>(s: string | undefined, valeurs: readonly T[], defaut: T): T {
  return valeurs.includes(s as T) ? s as T : defaut;
}
