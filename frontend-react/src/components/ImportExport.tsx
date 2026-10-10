/* Export CSV d'une période et import d'un relevé bancaire (correspondance des colonnes, aperçu avec
 * détection des doublons, puis enregistrement). */
import { useMemo, useRef, useState } from 'react';
import {
  Alert, Badge, Button, Checkbox, FileButton, Group, Select, SimpleGrid, Stack, Table, Text, TextInput,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useQueryClient } from '@tanstack/react-query';
import { IconDownload, IconFileImport, IconUpload, IconDatabaseExport } from '@tabler/icons-react';

import { api, toast } from '../lib/api';
import { lireCsv, lireDate, lireMontantCsv } from '../lib/csv';
import { fmt, jjmmaa } from '../lib/format';
import { T } from '../lib/palette';
import type { LigneImport, ResultatImport } from '../lib/types';
import { useConfig } from '../lib/queries';
import { Carte, Info, Pastille, Tableau } from './ui';

type Champ = 'date' | 'montant' | 'debit' | 'credit' | 'type' | 'description' | 'categorie' | 'tags';
const CHAMPS: { cle: Champ; label: string; aide?: string }[] = [
  { cle: 'date', label: 'Date *' },
  { cle: 'montant', label: 'Montant', aide: 'négatif = dépense' },
  { cle: 'debit', label: 'Débit', aide: 'si deux colonnes' },
  { cle: 'credit', label: 'Crédit', aide: 'si deux colonnes' },
  { cle: 'type', label: 'Type', aide: 'dépense / revenu' },
  { cle: 'description', label: 'Description' },
  { cle: 'categorie', label: 'Catégorie / source' },
  { cle: 'tags', label: 'Tags' },
];

/** Correspondance devinée d'après les en-têtes (dont ceux de l'export de l'application). Les motifs sont
 *  essayés dans l'ordre de préférence, et une colonne déjà attribuée n'est pas reprise (« Date opération »
 *  est la date, pas la description). */
function deviner(entetes: string[]): Partial<Record<Champ, string>> {
  const prises = new Set<number>();
  const trouve = (...motifs: RegExp[]) => {
    for (const m of motifs) {
      const i = entetes.findIndex((e, j) => !prises.has(j) && m.test(e.toLowerCase()));
      if (i >= 0) { prises.add(i); return String(i); }
    }
    return undefined;
  };
  const date = trouve(/^date/, /date/);
  const type = trouve(/^type$/);
  const categorie = trouve(/cat[ée]gor/, /^source$/);
  const montant = trouve(/^montant/, /amount/);
  const debit = trouve(/d[ée]bit/);
  const credit = trouve(/cr[ée]dit/);
  const tags = trouve(/^tags?$/);
  const description = trouve(/descr/, /libell/, /op[ée]ration/);
  return { date, montant, debit, credit, type, description, categorie, tags };
}

async function lireFichier(f: File): Promise<string> {
  const octets = await f.arrayBuffer();
  const utf8 = new TextDecoder('utf-8').decode(octets);
  // Relevé enregistré par Excel sous Windows : accents illisibles en UTF-8
  return utf8.includes('�') ? new TextDecoder('windows-1252').decode(octets) : utf8;
}

type LignePreparee = { ligne?: LigneImport; erreur?: string; brut: string[] };

/* ---------- Export ---------- */
function Export() {
  const [debut, setDebut] = useState<string | null>(null);
  const [fin, setFin] = useState<string | null>(null);
  const params = new URLSearchParams();
  if (debut) params.set('debut', debut);
  if (fin) params.set('fin', fin);
  return (
    <Stack gap="xs">
      <Text fz="xs" fw={700} c="dimmed" tt="uppercase" lts={0.5}>Exporter</Text>
      <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="xs">
        <DatePickerInput placeholder="Depuis le début" value={debut} onChange={setDebut} clearable valueFormat="DD/MM/YYYY" aria-label="Du" />
        <DatePickerInput placeholder="Jusqu'à aujourd'hui" value={fin} onChange={setFin} clearable valueFormat="DD/MM/YYYY" aria-label="Au" />
        <Button component="a" href={'/api/export/csv?' + params} download variant="default" leftSection={<IconDownload size={16} />}>
          Télécharger le CSV
        </Button>
      </SimpleGrid>
      <Info>Toutes les dépenses et tous les revenus de la période, lisibles dans Excel (séparateur « ; »).</Info>
    </Stack>
  );
}

/* ---------- Sauvegarde complète ---------- */
function Sauvegarde() {
  return (
    <Stack gap="xs">
      <Text fz="xs" fw={700} c="dimmed" tt="uppercase" lts={0.5}>Sauvegarde complète</Text>
      <Button component="a" href="/api/sauvegarde" download variant="default" leftSection={<IconDatabaseExport size={16} />} style={{ alignSelf: 'flex-start' }}>
        Télécharger toutes mes données
      </Button>
      <Info>
        Un seul fichier avec tout : Budget, Bourse, Lectures, Suivi et Patrimoine (sans ton mot de passe). Si les rappels sont configurés,
        une copie t'est aussi envoyée le 1er de chaque mois. Il se restaure avec le script « restaurer_sauvegarde.py ».
      </Info>
    </Stack>
  );
}

/* ---------- Import ---------- */
function Import() {
  const { data: config } = useConfig();
  const qc = useQueryClient();
  const [nomFichier, setNomFichier] = useState('');
  const [cellules, setCellules] = useState<string[][]>([]);
  const [avecEntetes, setAvecEntetes] = useState(true);
  const [colonnes, setColonnes] = useState<Partial<Record<Champ, string>>>({});
  const [positifsDepenses, setPositifsDepenses] = useState(false);
  const [categorieDefaut, setCategorieDefaut] = useState<string | null>(null);
  const [sourceDefaut, setSourceDefaut] = useState('');
  const [apercu, setApercu] = useState<ResultatImport | null>(null);
  const [envoi, setEnvoi] = useState(false);
  // Vide le champ fichier après lecture : sinon choisir à nouveau le même fichier ne déclenche rien
  const reinitialiserFichier = useRef<() => void>(null);

  const categories = config?.categories.map(c => c.nom) ?? [];
  const entetes = avecEntetes ? cellules[0] ?? [] : (cellules[0] ?? []).map((_, i) => `Colonne ${i + 1}`);
  const donnees = avecEntetes ? cellules.slice(1) : cellules;
  const optionsColonnes = entetes.map((e, i) => ({ value: String(i), label: e || `Colonne ${i + 1}` }));

  async function choisir(f: File | null) {
    if (!f) return;
    reinitialiserFichier.current?.();
    const c = lireCsv(await lireFichier(f));
    if (!c.length) return toast('Fichier vide ou illisible', false);
    setNomFichier(f.name);
    setCellules(c);
    setColonnes(deviner(c[0]));
    setApercu(null);
  }

  // Conversion de chaque ligne du fichier en opération (ou erreur lisible)
  const preparees: LignePreparee[] = useMemo(() => donnees.map(brut => {
    const val = (c: Champ) => colonnes[c] !== undefined ? brut[+colonnes[c]!] ?? '' : '';
    const date = lireDate(val('date'));
    if (!date) return { brut, erreur: `Date illisible : « ${val('date')} »` };
    let montant: number;
    if (colonnes.debit !== undefined || colonnes.credit !== undefined) {
      const debit = val('debit') ? Math.abs(lireMontantCsv(val('debit'))) : 0;
      const credit = val('credit') ? Math.abs(lireMontantCsv(val('credit'))) : 0;
      montant = credit - debit;
    } else montant = lireMontantCsv(val('montant'));
    if (isNaN(montant) || montant === 0) return { brut, erreur: 'Montant illisible ou nul' };
    const typeTexte = val('type').toLowerCase();
    const type: LigneImport['type'] = typeTexte
      ? (typeTexte.startsWith('rev') || typeTexte.startsWith('cr') ? 'revenu' : 'depense')
      : (montant < 0 || positifsDepenses ? 'depense' : 'revenu');
    // Catégorie du fichier si elle existe (sans tenir compte des majuscules), sinon celle par défaut
    const nomLu = val('categorie');
    const nom = type === 'depense'
      ? categories.find(c => c.toLowerCase() === nomLu.toLowerCase()) ?? categorieDefaut ?? ''
      : nomLu || sourceDefaut.trim();
    if (type === 'depense' && !nom) return { brut, erreur: 'Choisis une catégorie par défaut' };
    const tags = val('tags').split(',').map(t => t.trim()).filter(Boolean);
    return { brut, ligne: { type, date, nom, description: val('description'), montant: Math.abs(montant), tags } };
  }), [donnees, colonnes, positifsDepenses, categorieDefaut, sourceDefaut, categories]);   // eslint-disable-line react-hooks/exhaustive-deps

  const valides = preparees.filter(p => p.ligne).map(p => p.ligne!);

  async function envoyer(simulation: boolean) {
    setEnvoi(true);
    try {
      const r = await api<ResultatImport>('/api/import', { method: 'POST', body: { lignes: valides, simulation } });
      if (simulation) setApercu(r);
      else {
        toast(`${r.nb_ajoutees} opération${r.nb_ajoutees > 1 ? 's' : ''} importée${r.nb_ajoutees > 1 ? 's' : ''} ✓`
              + (r.nb_doublons ? ` · ${r.nb_doublons} doublon(s) ignoré(s)` : ''));
        qc.invalidateQueries({ queryKey: ['budget'] });
        setCellules([]); setApercu(null); setNomFichier('');
      }
    } catch { /* message déjà affiché */ } finally { setEnvoi(false); }
  }

  // Statut de chaque ligne du fichier : erreur locale, ou réponse de l'aperçu (dans l'ordre des lignes valides)
  let k = 0;
  const statuts = preparees.map(p => p.erreur
    ? { statut: 'erreur' as const, message: p.erreur }
    : apercu?.statuts[k++] ?? null);
  const nbAjout = statuts.filter(s => s?.statut === 'ajoutee').length;

  return (
    <Stack gap="sm">
      <Text fz="xs" fw={700} c="dimmed" tt="uppercase" lts={0.5}>Importer un relevé</Text>
      <Group gap="sm">
        <FileButton onChange={choisir} accept=".csv,.txt,text/csv" resetRef={reinitialiserFichier}>
          {props => <Button {...props} variant="default" leftSection={<IconUpload size={16} />}>Choisir un fichier CSV</Button>}
        </FileButton>
        {nomFichier && <Text fz="sm" c="dimmed">{nomFichier} · {donnees.length} ligne{donnees.length > 1 ? 's' : ''}</Text>}
      </Group>
      {!cellules.length ? (
        <Info>
          Exporte ton relevé en CSV depuis ta banque, puis associe ses colonnes. Un aperçu indique les doublons
          (même date, montant et description qu'une opération déjà saisie), qui ne seront pas réimportés.
        </Info>
      ) : (
        <>
          <Checkbox label="La première ligne contient les noms des colonnes" checked={avecEntetes}
                    onChange={e => { setAvecEntetes(e.currentTarget.checked); setApercu(null); }} />
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
            {CHAMPS.map(c => (
              <Select key={c.cle} label={c.label} description={c.aide} placeholder="—" data={optionsColonnes} clearable size="xs"
                      value={colonnes[c.cle] ?? null}
                      onChange={v => { setColonnes(x => ({ ...x, [c.cle]: v ?? undefined })); setApercu(null); }} />
            ))}
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xs">
            <Select label="Catégorie par défaut" description="dépenses sans catégorie reconnue" data={categories} searchable size="xs"
                    value={categorieDefaut} onChange={v => { setCategorieDefaut(v); setApercu(null); }} />
            <TextInput label="Source par défaut" description="revenus sans source" placeholder="ex : Salaire" size="xs"
                       value={sourceDefaut} onChange={e => { setSourceDefaut(e.currentTarget.value); setApercu(null); }} />
            <Checkbox mt={{ sm: 'xl' }} label="Montants positifs = dépenses (relevé de carte)" checked={positifsDepenses}
                      disabled={colonnes.type !== undefined || colonnes.debit !== undefined || colonnes.credit !== undefined}
                      onChange={e => { setPositifsDepenses(e.currentTarget.checked); setApercu(null); }} />
          </SimpleGrid>

          <Tableau minWidth={640}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Date</Table.Th><Table.Th>Catégorie / source</Table.Th><Table.Th>Description</Table.Th>
                <Table.Th className="num">Montant</Table.Th><Table.Th>Statut</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {preparees.slice(0, 200).map((p, i) => {
                const s = statuts[i];
                return (
                  <Table.Tr key={i} style={{ opacity: s?.statut === 'doublon' ? 0.5 : 1 }}>
                    <Table.Td c="dimmed" style={{ whiteSpace: 'nowrap' }}>{p.ligne ? jjmmaa(p.ligne.date) : p.brut[+(colonnes.date ?? 0)]}</Table.Td>
                    <Table.Td>{p.ligne?.nom}</Table.Td>
                    <Table.Td>{p.ligne?.description}</Table.Td>
                    <Table.Td className="num chiffre" c={p.ligne?.type === 'depense' ? T.dep : T.rev}>
                      {p.ligne ? (p.ligne.type === 'depense' ? '− ' : '+ ') + fmt(p.ligne.montant) : ''}
                    </Table.Td>
                    <Table.Td>
                      {s ? <Badge size="sm" variant="light" color={s.statut === 'ajoutee' ? 'emeraude' : s.statut === 'doublon' ? 'gray' : 'rouge'}
                                  title={s.message}>
                             {s.statut === 'ajoutee' ? 'nouvelle' : s.statut === 'doublon' ? 'doublon' : s.message}
                           </Badge> : <Text fz="xs" c="dimmed">—</Text>}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Tableau>
          {preparees.length > 200 && <Info>Aperçu limité aux 200 premières lignes ; toutes seront importées.</Info>}

          {!apercu ? (
            <Button leftSection={<IconFileImport size={16} />} onClick={() => envoyer(true)} loading={envoi} disabled={!valides.length}
                    style={{ alignSelf: 'flex-start' }}>
              Vérifier {valides.length} ligne{valides.length > 1 ? 's' : ''}
            </Button>
          ) : (
            <Alert color={nbAjout ? 'emeraude' : 'gray'} variant="light">
              <Group justify="space-between" wrap="wrap" gap="sm">
                <Text fz="sm">
                  {nbAjout} nouvelle{nbAjout > 1 ? 's' : ''} · {apercu.nb_doublons} doublon{apercu.nb_doublons > 1 ? 's' : ''} ignoré{apercu.nb_doublons > 1 ? 's' : ''}
                  {statuts.filter(s => s?.statut === 'erreur').length ? ` · ${statuts.filter(s => s?.statut === 'erreur').length} en erreur (ignorées)` : ''}
                </Text>
                <Button onClick={() => envoyer(false)} loading={envoi} disabled={!nbAjout}>Importer {nbAjout} opération{nbAjout > 1 ? 's' : ''}</Button>
              </Group>
            </Alert>
          )}
        </>
      )}
    </Stack>
  );
}

export function ImportExport() {
  return (
    <Carte titre="Import / export" description="Sauvegarde toutes tes données, exporte le Budget, ou charge un relevé bancaire"
           icone={<Pastille icone={IconFileImport} couleur="gray" />}>
      <Stack gap="lg">
        <Sauvegarde />
        <Export />
        <Import />
      </Stack>
    </Carte>
  );
}
