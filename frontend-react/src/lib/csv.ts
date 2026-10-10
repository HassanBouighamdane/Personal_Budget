/* Lecture d'un fichier CSV (relevé bancaire, export de l'application) pour l'import */

/** Séparateur le plus fréquent dans la première ligne : « ; », « , » ou tabulation */
export function detecterSeparateur(texte: string): string {
  const ligne = texte.split(/\r?\n/, 1)[0] ?? '';
  const compte = (c: string) => ligne.split(c).length - 1;
  return [';', '\t', ','].reduce((a, b) => compte(b) > compte(a) ? b : a, ';');
}

/** CSV → lignes de cellules (guillemets doublés et retours à la ligne entre guillemets gérés) */
export function lireCsv(texte: string, sep = detecterSeparateur(texte)): string[][] {
  const lignes: string[][] = [];
  let ligne: string[] = [], cellule = '', guillemets = false;
  texte = texte.replace(/^﻿/, '');
  for (let i = 0; i < texte.length; i++) {
    const c = texte[i];
    if (guillemets) {
      if (c === '"' && texte[i + 1] === '"') { cellule += '"'; i++; }
      else if (c === '"') guillemets = false;
      else cellule += c;
    } else if (c === '"') guillemets = true;
    else if (c === sep) { ligne.push(cellule); cellule = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && texte[i + 1] === '\n') i++;
      ligne.push(cellule); cellule = '';
      if (ligne.some(x => x.trim())) lignes.push(ligne);
      ligne = [];
    } else cellule += c;
  }
  ligne.push(cellule);
  if (ligne.some(x => x.trim())) lignes.push(ligne);
  return lignes.map(l => l.map(x => x.trim()));
}

/** « 2026-09-18 », « 18/09/2026 », « 18-09-2026 », « 18.09.26 » → AAAA-MM-JJ ; null si illisible */
export function lireDate(v: string): string | null {
  let a: number, m: number, j: number;
  const iso = v.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  const fr = v.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\b/);
  if (iso) [a, m, j] = [+iso[1], +iso[2], +iso[3]];
  else if (fr) [j, m, a] = [+fr[1], +fr[2], fr[3].length === 2 ? 2000 + +fr[3] : +fr[3]];
  else return null;
  const d = new Date(a, m - 1, j);
  if (d.getFullYear() !== a || d.getMonth() !== m - 1 || d.getDate() !== j) return null;
  return `${a}-${String(m).padStart(2, '0')}-${String(j).padStart(2, '0')}`;
}

/** « -1 234,56 DH », « 1,234.56 », « (45,00) » → nombre signé ; NaN si illisible.
 *  Avec les deux séparateurs, le dernier est la virgule décimale. */
export function lireMontantCsv(v: string): number {
  let s = v.replace(/[\s  ]/g, '').replace(/[^\d,.\-()+]/g, '');
  const negatif = s.startsWith('-') || s.endsWith('-') || (s.startsWith('(') && s.endsWith(')'));
  s = s.replace(/[-+()]/g, '');
  const virgule = s.lastIndexOf(','), point = s.lastIndexOf('.');
  if (virgule >= 0 && point >= 0) {
    s = virgule > point ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
  } else if (virgule >= 0) {
    // « 1,234 » (milliers à l'anglaise) ou « 12,5 » (décimale) : 3 chiffres après une seule virgule = milliers
    s = /^\d{1,3}(,\d{3})+$/.test(s) ? s.replace(/,/g, '') : s.replace(',', '.');
  }
  const n = parseFloat(s);
  return isNaN(n) ? NaN : Math.round((negatif ? -n : n) * 100) / 100;
}
