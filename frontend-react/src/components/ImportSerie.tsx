/* Fenêtre d'import d'une série de valeurs datées (cours passés d'un titre, valeurs passées d'un indice) depuis un fichier
 * .xlsx, .csv ou un export « Excel » en HTML. Colonnes date et valeur devinées (modifiables), dates jour/mois ou mois/jour,
 * aperçu avant l'envoi. Le serveur garde les valeurs déjà notées le soir et refuse le fichier d'une autre série. */
import { useState, type ReactNode } from 'react';
import { Alert, Button, FileInput, Select, SimpleGrid, Stack, Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconFileImport, IconInfoCircle } from '@tabler/icons-react';

import { toast } from '../lib/api';
import { lireMontantCsv } from '../lib/csv';
import { auj, dateFr } from '../lib/format';
import { dateSerieExcel, lireTableau } from '../lib/tableur';
import { useEcriture } from '../lib/queries';

type FormatDate = 'jm' | 'mj';
export type ResultatImportSerie = { importees: number; deja_notees: number; debut: string; fin: string };

/** « 18/09/2026 » lu en jour/mois ou mois/jour (les fichiers en anglais sont en mois/jour), AAAA-MM-JJ, ou date Excel */
export function lireDateFormat(v: string, format: FormatDate): string | null {
  const iso = v.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  const court = v.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\b/);
  let a: number, m: number, j: number;
  if (iso) [a, m, j] = [+iso[1], +iso[2], +iso[3]];
  else if (court) {
    const [x, y] = [+court[1], +court[2]];
    [j, m] = format === 'jm' ? [x, y] : [y, x];
    a = court[3].length === 2 ? 2000 + +court[3] : +court[3];
  } else return dateSerieExcel(v);
  const d = new Date(a, m - 1, j);
  if (d.getFullYear() !== a || d.getMonth() !== m - 1 || d.getDate() !== j) return null;
  return `${a}-${String(m).padStart(2, '0')}-${String(j).padStart(2, '0')}`;
}

/** Format des dates deviné : un premier nombre au-delà de 12 → jour/mois, un second → mois/jour */
export function devinerFormat(dates: string[]): FormatDate {
  for (const v of dates) {
    const c = v.match(/^(\d{1,2})[/.-](\d{1,2})[/.-]/);
    if (c && +c[1] > 12) return 'jm';
    if (c && +c[2] > 12) return 'mj';
  }
  return 'jm';
}

/** Début des données : la première ligne qui contient une date. L'en-tête est la ligne juste avant
 *  (un export peut commencer par un titre ou des lignes vides). */
export function decouper(lignes: string[][]): { entete: string[]; donnees: string[][]; colDate: number } {
  for (let i = 0; i < Math.min(lignes.length, 40); i++) {
    const col = lignes[i].findIndex(c => !!lireDateFormat(c, 'jm') || !!lireDateFormat(c, 'mj'));
    if (col >= 0) {
      const largeur = Math.max(...lignes.slice(i, i + 20).map(l => l.length));
      const entete = Array.from({ length: largeur }, (_, k) => (i > 0 ? lignes[i - 1][k] : '') || `Colonne ${k + 1}`);
      return { entete, donnees: lignes.slice(i), colDate: col };
    }
  }
  return { entete: lignes[0] ?? [], donnees: [], colDate: 0 };
}

/** Colonne de la valeur : la clôture d'abord (« Cours de clôture », « Dernier cours », « Close »), sinon un prix ou une
 *  valeur, sinon la première colonne de nombres après la date */
export function devinerColonne(entete: string[], donnees: string[][], colDate: number): number {
  for (const motif of [/cl[oô]ture|dernier|close|last/i, /price|valeur|value|cours|prix/i]) {
    const i = entete.findIndex((e, k) => k !== colDate && motif.test(e) && !/ouverture|open|veille|variation|volume/i.test(e));
    if (i >= 0) return i;
  }
  const largeur = entete.length;
  for (let k = 0; k < largeur; k++) {
    if (k !== colDate && donnees.slice(0, 10).every(l => lireMontantCsv(l[k] ?? '') > 0)) return k;
  }
  return colDate === 0 ? 1 : 0;
}

function FenetreImportSerie({ titre, series, initial, chemin, module, aide, debutConseille, avertissement, fermer }: {
  titre: string; series: { value: string; label: string }[]; initial: string; chemin: (code: string) => string;
  module: 'bourse'; aide: ReactNode; debutConseille: (code: string) => string | null; avertissement?: (code: string) => ReactNode;
  fermer: () => void;
}) {
  const ecrire = useEcriture(module);
  const [code, setCode] = useState(initial);
  const [fichier, setFichier] = useState<File | null>(null);
  const [lu, setLu] = useState<ReturnType<typeof decouper> | null>(null);
  const [colDate, setColDate] = useState('0');
  const [colValeur, setColValeur] = useState('1');
  const [format, setFormat] = useState<FormatDate>('jm');

  async function charger(f: File | null) {
    setFichier(f);
    setLu(null);
    if (!f) return;
    try {
      const d = decouper(await lireTableau(f));
      if (!d.donnees.length) return toast('Aucune date trouvée dans ce fichier', false);
      setLu(d);
      setColDate(String(d.colDate));
      setColValeur(String(devinerColonne(d.entete, d.donnees, d.colDate)));
      setFormat(devinerFormat(d.donnees.map(l => l[d.colDate] ?? '')));
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Fichier illisible', false);
    }
  }

  const valeurs = (lu?.donnees ?? [])
    .map(l => ({ date: lireDateFormat(l[+colDate] ?? '', format), valeur: lireMontantCsv(l[+colValeur] ?? '') }))
    .filter((v): v is { date: string; valeur: number } => !!v.date && v.valeur > 0 && v.date <= auj())
    .sort((a, b) => a.date.localeCompare(b.date));
  // Une même date en double (fichier mal découpé) : la dernière ligne lue l'emporte
  const parDate = [...new Map(valeurs.map(v => [v.date, v])).values()];
  const ignorees = Math.max(0, (lu?.donnees.length ?? 0) - parDate.length);
  const conseille = debutConseille(code);
  const colonnes = (lu?.entete ?? []).map((e, i) => ({ value: String(i), label: e }));

  function importer() {
    ecrire.mutate({ path: chemin(code), method: 'POST', body: { valeurs: parDate } }, {
      onSuccess: r => {
        const x = r as ResultatImportSerie;
        toast(`${x.importees} valeur${x.importees > 1 ? 's' : ''} importée${x.importees > 1 ? 's' : ''}` +
              (x.deja_notees ? ` (${x.deja_notees} déjà notée${x.deja_notees > 1 ? 's' : ''} le soir, gardée${x.deja_notees > 1 ? 's' : ''})` : '') + ' ✓');
        fermer();
      },
    });
  }

  return (
    <Stack gap="sm">
      <Text fz="sm" c="dimmed">{aide}</Text>
      <Select label={titre} data={series} value={code} onChange={v => v && setCode(v)} allowDeselect={false} searchable
              comboboxProps={{ withinPortal: true }} />
      {avertissement?.(code)}
      <FileInput label="Fichier (.xlsx ou .csv)" placeholder="Choisir un fichier" accept=".xlsx,.csv,.txt,.xls,text/csv" value={fichier}
                 onChange={charger} leftSection={<IconFileImport size={16} />} clearable />
      {lu && (
        <>
          <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="sm">
            <Select label="Colonne date" data={colonnes} value={colDate} onChange={v => v && setColDate(v)} allowDeselect={false}
                    comboboxProps={{ withinPortal: true }} />
            <Select label="Colonne valeur" data={colonnes} value={colValeur} onChange={v => v && setColValeur(v)} allowDeselect={false}
                    comboboxProps={{ withinPortal: true }} />
            <Select label="Dates" data={[{ value: 'jm', label: 'jour/mois (18/09/2026)' }, { value: 'mj', label: 'mois/jour (09/18/2026)' }]}
                    value={format} onChange={v => v && setFormat(v as FormatDate)} allowDeselect={false} comboboxProps={{ withinPortal: true }} />
          </SimpleGrid>
          {parDate.length ? (
            <Alert variant="light" color="bleu" radius="md" icon={<IconInfoCircle size={16} />}>
              <Text fz="sm">
                {parDate.length} valeurs, du {dateFr(parDate[0].date)} ({parDate[0].valeur.toLocaleString('fr-FR')}) au {dateFr(parDate.at(-1)!.date)} ({parDate.at(-1)!.valeur.toLocaleString('fr-FR')})
                {ignorees ? ` · ${ignorees} ligne${ignorees > 1 ? 's' : ''} ignorée${ignorees > 1 ? 's' : ''}` : ''}
              </Text>
              {conseille && parDate[0].date > conseille && (
                <Text fz="xs" c="ambre" mt={4}>Le fichier commence après le {dateFr(conseille)} : les jours d'avant resteront estimés.</Text>
              )}
            </Alert>
          ) : <Text fz="sm" c="rouge">Aucune ligne lisible : vérifie les colonnes et le format des dates.</Text>}
        </>
      )}
      <Button onClick={importer} loading={ecrire.isPending} disabled={!parDate.length}>Importer {parDate.length || ''} valeurs</Button>
    </Stack>
  );
}

export function ouvrirImportSerie(props: Omit<Parameters<typeof FenetreImportSerie>[0], 'fermer'> & { titreFenetre: string }) {
  const { titreFenetre, ...reste } = props;
  const id = modals.open({ title: <Text fw={650}>{titreFenetre}</Text>, centered: true, size: 'lg',
                           children: <FenetreImportSerie {...reste} fermer={() => modals.close(id)} /> });
}
