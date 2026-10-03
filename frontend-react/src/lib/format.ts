/* Formatage en français : montants, dates (AAAA-MM-JJ côté API) */
export const MOIS_FR = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
export const JOURS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

/** Montant en DH : 1 234,5 DH */
export const fmt = (v: number | string) => (+v).toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' DH';

/** Nombre sans unité (axes des graphiques) */
export const nombreFr = (v: number | string) => Number(v).toLocaleString('fr-FR');

/** Montant saisi en texte : accepte virgule ou point et les espaces ; NaN si invalide */
export function lireMontant(texte: string): number {
  const v = parseFloat(texte.trim().replace(/\s/g, '').replace(',', '.'));
  return isNaN(v) ? NaN : Math.round(v * 100) / 100;
}

const iso = (d: Date) =>
  d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');

/** Date du jour AAAA-MM-JJ (heure locale) */
export const auj = () => iso(new Date());

export function decalerDate(date: string, jours: number): string {
  const [a, m, j] = date.split('-').map(Number);
  return iso(new Date(a, m - 1, j + jours));
}

/** Décale un mois AAAA-MM de `delta` mois */
export function decalerMois(mois: string, delta: number): string {
  let [a, m] = mois.split('-').map(Number);
  m += delta;
  while (m <= 0) { m += 12; a--; }
  while (m > 12) { m -= 12; a++; }
  return a + '-' + String(m).padStart(2, '0');
}

/** 18 septembre 2026 (ou 18 septembre sans l'année) */
export function dateFr(date: string, avecAnnee = true): string {
  const [a, m, j] = date.split('-').map(Number);
  return j + ' ' + MOIS_FR[m - 1].toLowerCase() + (avecAnnee ? ' ' + a : '');
}

export function nomJour(date: string): string {
  const [a, m, j] = date.split('-').map(Number);
  return JOURS_FR[(new Date(a, m - 1, j).getDay() + 6) % 7];
}

/** AAAA-MM → Septembre 2026 */
export const libelleMois = (mois: string) => MOIS_FR[+mois.slice(5, 7) - 1] + ' ' + mois.slice(0, 4);
/** AAAA-MM → Sept. 2026 */
export const moisCourt = (mois: string) => MOIS_FR[+mois.slice(5, 7) - 1].slice(0, 4) + '. ' + mois.slice(0, 4);
/** AAAA-MM-JJ → JJ/MM */
export const jjmm = (d: string) => `${d.slice(8)}/${d.slice(5, 7)}`;
/** AAAA-MM-JJ → JJ/MM/AA */
export const jjmmaa = (d: string) => `${d.slice(8)}/${d.slice(5, 7)}/${d.slice(2, 4)}`;
