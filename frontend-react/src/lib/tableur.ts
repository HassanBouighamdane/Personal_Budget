/* Lecture d'un fichier de tableur dans le navigateur, sans bibliothèque : .xlsx (une archive zip de fichiers XML, décompressée
 * par le navigateur), « Excel » qui est en fait un tableau HTML (export fréquent des sites), ou CSV. Renvoie des lignes de
 * cellules en texte ; une date stockée par Excel reste son numéro de série (cf. dateSerieExcel). */
import { lireCsv } from './csv';

const SIG_FIN_REPERTOIRE = 0x06054b50, SIG_ENTREE = 0x02014b50, SIG_LOCAL = 0x04034b50;

/** Fichiers d'une archive zip : nom → fonction qui le décompresse (seulement ceux qu'on lit) */
function lireZip(octets: Uint8Array): Map<string, () => Promise<Uint8Array>> {
  const v = new DataView(octets.buffer, octets.byteOffset, octets.byteLength);
  let fin = -1;
  for (let i = octets.length - 22; i >= Math.max(0, octets.length - 65557); i--) {
    if (v.getUint32(i, true) === SIG_FIN_REPERTOIRE) { fin = i; break; }
  }
  if (fin < 0) throw new Error('Archive zip illisible');
  const nb = v.getUint16(fin + 10, true);
  let p = v.getUint32(fin + 16, true);
  const fichiers = new Map<string, () => Promise<Uint8Array>>();
  const nomDe = new TextDecoder();
  for (let k = 0; k < nb; k++) {
    if (v.getUint32(p, true) !== SIG_ENTREE) throw new Error('Archive zip illisible');
    const methode = v.getUint16(p + 10, true), taille = v.getUint32(p + 20, true);
    const lnNom = v.getUint16(p + 28, true), lnExtra = v.getUint16(p + 30, true), lnComm = v.getUint16(p + 32, true);
    const local = v.getUint32(p + 42, true);
    const nom = nomDe.decode(octets.subarray(p + 46, p + 46 + lnNom));
    fichiers.set(nom, async () => {
      if (v.getUint32(local, true) !== SIG_LOCAL) throw new Error('Archive zip illisible');
      const debut = local + 30 + v.getUint16(local + 26, true) + v.getUint16(local + 28, true);
      const brut = octets.subarray(debut, debut + taille);
      if (methode === 0) return brut;
      if (methode !== 8) throw new Error('Compression non prise en charge');
      const flux = new Blob([brut.slice()]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      return new Uint8Array(await new Response(flux).arrayBuffer());
    });
    p += 46 + lnNom + lnExtra + lnComm;
  }
  return fichiers;
}

/** Numéro de colonne d'une référence de cellule : « C12 » → 2 */
function colonne(ref: string): number {
  let n = 0;
  for (const c of ref.replace(/\d+$/, '')) n = n * 26 + c.charCodeAt(0) - 64;
  return n - 1;
}

const xml = (texte: string) => new DOMParser().parseFromString(texte, 'application/xml');
/** Éléments d'un nom donné, quel que soit leur espace de noms */
const elements = (racine: Document | Element, nom: string) => Array.from(racine.getElementsByTagNameNS('*', nom));

async function lireXlsx(octets: Uint8Array): Promise<string[][]> {
  const zip = lireZip(octets);
  const texte = async (nom: string) => new TextDecoder().decode(await zip.get(nom)!());
  const partagees = zip.has('xl/sharedStrings.xml')
    ? elements(xml(await texte('xl/sharedStrings.xml')), 'si').map(si => elements(si, 't').map(t => t.textContent ?? '').join(''))
    : [];
  // Première feuille : celle du classeur, sinon la première trouvée
  let feuille = 'xl/worksheets/sheet1.xml';
  if (!zip.has(feuille)) feuille = [...zip.keys()].filter(n => /^xl\/worksheets\/[^/]+\.xml$/.test(n)).sort()[0];
  if (!feuille) throw new Error('Aucune feuille dans ce classeur');
  const lignes: string[][] = [];
  for (const row of elements(xml(await texte(feuille)), 'row')) {
    const ligne: string[] = [];
    for (const c of elements(row, 'c')) {
      const type = c.getAttribute('t'), ref = c.getAttribute('r');
      const v = elements(c, 'v')[0]?.textContent ?? '';
      const valeur = type === 's' ? partagees[+v] ?? '' : type === 'inlineStr' ? elements(c, 't').map(t => t.textContent).join('') : v;
      ligne[ref ? colonne(ref) : ligne.length] = valeur.trim();
    }
    const pleine = Array.from(ligne, x => x ?? '');
    if (pleine.some(x => x)) lignes.push(pleine);
  }
  return lignes;
}

function lireTableauHtml(texte: string): string[][] {
  const doc = new DOMParser().parseFromString(texte, 'text/html');
  return Array.from(doc.querySelectorAll('tr'))
    .map(tr => Array.from(tr.querySelectorAll('th,td')).map(c => (c.textContent ?? '').replace(/\s+/g, ' ').trim()))
    .filter(l => l.some(x => x));
}

/** Lignes de cellules d'un fichier .xlsx, .csv / .txt ou d'un export « Excel » en HTML */
export async function lireTableau(fichier: File): Promise<string[][]> {
  const octets = new Uint8Array(await fichier.arrayBuffer());
  if (octets[0] === 0x50 && octets[1] === 0x4b) return lireXlsx(octets);              // « PK » : zip, donc .xlsx
  if (octets[0] === 0xd0 && octets[1] === 0xcf) {
    throw new Error('Ancien format Excel (.xls) : ouvre-le et enregistre-le en .xlsx ou en CSV');
  }
  const texte = new TextDecoder().decode(octets);
  if (/<table/i.test(texte.slice(0, 5000))) return lireTableauHtml(texte);
  return lireCsv(texte);
}

/** Date stockée par Excel (jours depuis le 30/12/1899) → AAAA-MM-JJ ; null hors des années 1955–2119 */
export function dateSerieExcel(v: string): string | null {
  if (!/^\d{5}(\.\d+)?$/.test(v)) return null;
  const n = Math.floor(+v);
  if (n < 20000 || n > 80000) return null;
  return new Date(Date.UTC(1899, 11, 30) + n * 86400000).toISOString().slice(0, 10);
}
