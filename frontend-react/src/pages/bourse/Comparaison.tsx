/* Bourse — comparaison avec un indice : le compte Bourse face au même argent (mêmes apports, mêmes dates) placé dans l'indice.
 * Les versions « Rentabilité Net » réinvestissent les dividendes : ce sont elles qui se comparent honnêtement au compte.
 * Import des valeurs passées d'un indice (fichier CSV), pour couvrir les apports antérieurs à l'historique. */
import { useState } from 'react';
import {
  Alert, Badge, Box, Button, FileInput, Group, Select, SimpleGrid, Stack, Table, Text, Tooltip,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconChartArrowsVertical, IconFileImport, IconInfoCircle } from '@tabler/icons-react';
import type { ChartData } from 'chart.js';

import { toast } from '../../lib/api';
import { lireCsv, lireMontantCsv } from '../../lib/csv';
import { auj, dateFr, fmt, jjmm, jjmmaa } from '../../lib/format';
import { C, signe } from '../../lib/palette';
import type { IndiceSuivi, ResultatImportIndice } from '../../lib/types';
import { useComparaison, useEcriture, useIndices } from '../../lib/queries';
import { Graphique, optionsSeries } from '../../components/Graphique';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Tableau } from '../../components/ui';

const pct = (v: number) => (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(1).replace('.', ',') + ' %';
const libelleIndice = (i: Pick<IndiceSuivi, 'nom' | 'dividendes'>) => i.nom + (i.dividendes ? '' : ' (hors dividendes)');

/* ---------- Import d'un fichier ---------- */
type FormatDate = 'jm' | 'mj';

/** « 18/09/2026 » lu en jour/mois ou mois/jour (les fichiers en anglais sont en mois/jour), ou AAAA-MM-JJ */
function lireDateFormat(v: string, format: FormatDate): string | null {
  const iso = v.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  const court = v.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\b/);
  let a: number, m: number, j: number;
  if (iso) [a, m, j] = [+iso[1], +iso[2], +iso[3]];
  else if (court) {
    const [x, y] = [+court[1], +court[2]];
    [j, m] = format === 'jm' ? [x, y] : [y, x];
    a = court[3].length === 2 ? 2000 + +court[3] : +court[3];
  } else return null;
  const d = new Date(a, m - 1, j);
  if (d.getFullYear() !== a || d.getMonth() !== m - 1 || d.getDate() !== j) return null;
  return `${a}-${String(m).padStart(2, '0')}-${String(j).padStart(2, '0')}`;
}

/** Format des dates deviné : un premier nombre au-delà de 12 → jour/mois, un second → mois/jour */
function devinerFormat(dates: string[]): FormatDate {
  for (const v of dates) {
    const c = v.match(/^(\d{1,2})[/.-](\d{1,2})[/.-]/);
    if (c && +c[1] > 12) return 'jm';
    if (c && +c[2] > 12) return 'mj';
  }
  return 'jm';
}

/** Colonne de la valeur : celle dont l'en-tête dit « clôture / dernier / close / price / valeur », sinon la 2e */
function devinerColonne(entete: string[]): number {
  const i = entete.findIndex(e => /cl[oô]ture|dernier|close|price|valeur|value|cours/i.test(e));
  return i >= 0 ? i : Math.min(1, entete.length - 1);
}

function FenetreImport({ initial, fermer }: { initial: string; fermer: () => void }) {
  const { data: indices } = useIndices();
  const ecrire = useEcriture('bourse');
  const [code, setCode] = useState(initial);
  const [lignes, setLignes] = useState<string[][]>([]);
  const [colDate, setColDate] = useState('0');
  const [colValeur, setColValeur] = useState('1');
  const [format, setFormat] = useState<FormatDate>('jm');
  const [nomFichier, setNomFichier] = useState<File | null>(null);

  async function charger(f: File | null) {
    setNomFichier(f);
    if (!f) return setLignes([]);
    const l = lireCsv(await f.text());
    if (l.length < 2) return toast('Fichier vide ou illisible', false);
    setLignes(l);
    setColDate(String(Math.max(0, l[0].findIndex(e => /date/i.test(e)))));
    setColValeur(String(devinerColonne(l[0])));
    setFormat(devinerFormat(l.slice(1).map(x => x[Math.max(0, l[0].findIndex(e => /date/i.test(e)))] ?? '')));
  }

  const entete = lignes[0] ?? [];
  const valeurs = lignes.slice(1).map(x => ({ date: lireDateFormat(x[+colDate] ?? '', format), valeur: lireMontantCsv(x[+colValeur] ?? '') }))
    .filter((v): v is { date: string; valeur: number } => !!v.date && v.valeur > 0 && v.date <= auj())
    .sort((a, b) => a.date.localeCompare(b.date));
  const illisibles = Math.max(0, lignes.length - 1 - valeurs.length);
  const choisi = indices?.indices.find(i => i.code === code);

  function importer() {
    ecrire.mutate({ path: `/api/bourse/indices/${code}/import`, method: 'POST', body: { valeurs } }, {
      onSuccess: r => {
        const x = r as ResultatImportIndice;
        toast(`${x.importees} valeur${x.importees > 1 ? 's' : ''} importée${x.importees > 1 ? 's' : ''}` +
              (x.deja_notees ? ` (${x.deja_notees} déjà notée${x.deja_notees > 1 ? 's' : ''}, gardée${x.deja_notees > 1 ? 's' : ''})` : '') + ' ✓');
        fermer();
      },
    });
  }

  return (
    <Stack gap="sm">
      <Text fz="sm" c="dimmed">
        Les valeurs passées de l'indice couvrent tes apports d'avant le début de l'historique. Télécharge son historique
        (cours de clôture journaliers, ou au moins un par mois depuis ton premier apport{indices?.premier_mouvement ? `, le ${dateFr(indices.premier_mouvement)}` : ''})
        depuis le site de la Bourse de Casablanca ou un site financier, au format CSV.
      </Text>
      <Select label="Indice" data={(indices?.indices ?? []).map(i => ({ value: i.code, label: libelleIndice(i) }))} value={code}
              onChange={v => v && setCode(v)} allowDeselect={false} comboboxProps={{ withinPortal: true }} />
      {choisi && !choisi.dividendes && (
        <Text fz="xs" c="dimmed">Vérifie que le fichier est bien celui de « {choisi.nom} » et non de sa version Rentabilité : leurs valeurs n'ont rien à voir.</Text>
      )}
      <FileInput label="Fichier CSV" placeholder="Choisir un fichier" accept=".csv,.txt,text/csv" value={nomFichier} onChange={charger}
                 leftSection={<IconFileImport size={16} />} clearable />
      {lignes.length > 1 && (
        <>
          <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="sm">
            <Select label="Colonne date" data={entete.map((e, i) => ({ value: String(i), label: e || `Colonne ${i + 1}` }))} value={colDate}
                    onChange={v => v && setColDate(v)} allowDeselect={false} comboboxProps={{ withinPortal: true }} />
            <Select label="Colonne valeur" data={entete.map((e, i) => ({ value: String(i), label: e || `Colonne ${i + 1}` }))} value={colValeur}
                    onChange={v => v && setColValeur(v)} allowDeselect={false} comboboxProps={{ withinPortal: true }} />
            <Select label="Dates" data={[{ value: 'jm', label: 'jour/mois (18/09/2026)' }, { value: 'mj', label: 'mois/jour (09/18/2026)' }]}
                    value={format} onChange={v => v && setFormat(v as FormatDate)} allowDeselect={false} comboboxProps={{ withinPortal: true }} />
          </SimpleGrid>
          {valeurs.length ? (
            <Alert variant="light" color="bleu" radius="md" icon={<IconInfoCircle size={16} />}>
              <Text fz="sm">
                {valeurs.length} valeurs, du {dateFr(valeurs[0].date)} ({valeurs[0].valeur.toLocaleString('fr-FR')}) au {dateFr(valeurs.at(-1)!.date)} ({valeurs.at(-1)!.valeur.toLocaleString('fr-FR')})
                {illisibles ? ` · ${illisibles} ligne${illisibles > 1 ? 's' : ''} ignorée${illisibles > 1 ? 's' : ''}` : ''}
              </Text>
              {indices?.premier_mouvement && valeurs[0].date > indices.premier_mouvement && (
                <Text fz="xs" c="ambre" mt={4}>Ton premier apport ({dateFr(indices.premier_mouvement)}) reste avant ce fichier : la comparaison restera incomplète.</Text>
              )}
            </Alert>
          ) : <Text fz="sm" c="rouge">Aucune ligne lisible : vérifie les colonnes et le format des dates.</Text>}
        </>
      )}
      <Button onClick={importer} loading={ecrire.isPending} disabled={!valeurs.length}>Importer {valeurs.length || ''} valeurs</Button>
    </Stack>
  );
}

export function ouvrirImportIndice(code: string) {
  const id = modals.open({ title: <Text fw={650}>Importer l'historique d'un indice</Text>, centered: true, size: 'lg',
                           children: <FenetreImport initial={code} fermer={() => modals.close(id)} /> });
}

/* ---------- Comparaison (tableau de bord Bourse) ---------- */
function Colonne({ titre, valeur, rendement }: { titre: string; valeur: number; rendement: number | null }) {
  return (
    <Box>
      <Text fz="xs" c="dimmed">{titre}</Text>
      <Text className="chiffre" fz={20} fw={700}>{fmt(valeur)}</Text>
      <Text fz="sm" c={rendement === null ? 'dimmed' : signe(rendement)} fw={600}>
        {rendement === null ? 'rendement annuel après 90 jours' : `${pct(rendement)} par an`}
      </Text>
    </Box>
  );
}

export function CarteComparaison() {
  const { data: indices } = useIndices();
  const [code, setCode] = useState<string | null>(null);
  const actif = code ?? indices?.defaut ?? 'MASRN';
  const { data: c, isPending } = useComparaison(actif);
  const choix = (
    <Select size="xs" w={240} data={(indices?.indices ?? []).map(i => ({ value: i.code, label: libelleIndice(i) }))} value={actif}
            onChange={v => v && setCode(v)} allowDeselect={false} aria-label="Indice de référence" comboboxProps={{ withinPortal: true }} />
  );
  const points = c?.points ?? [];
  const format = points.length && points[0].date.slice(0, 4) !== points.at(-1)!.date.slice(0, 4) ? jjmmaa : jjmm;
  const base = optionsSeries();

  return (
    <Carte titre="Comparaison avec l'indice" icone={<Pastille icone={IconChartArrowsVertical} couleur="marque" />} droite={choix}
           description="Tes apports et retraits, aux mêmes dates, placés dans l'indice">
      {isPending || !c ? <Chargement lignes={3} /> : c.etat === 'sans_apport' ? (
        <Info>Saisis tes apports au compte Bourse (onglet Mouvements) : la comparaison place les mêmes sommes dans l'indice.</Info>
      ) : c.etat !== 'ok' ? (
        <Stack gap="sm">
          <Info>
            {c.etat === 'vide'
              ? <>Aucune valeur de {c.nom} pour l'instant : elle est notée chaque soir de bourse à partir d'aujourd'hui.</>
              : <>Ton premier apport date du {dateFr(c.manque_avant!)}, avant les valeurs connues de {c.nom}.</>}
            {' '}Importe son historique depuis ce jour-là pour comparer tout ton compte.
          </Info>
          <Button variant="light" leftSection={<IconFileImport size={16} />} onClick={() => ouvrirImportIndice(c.indice)} style={{ alignSelf: 'flex-start' }}>
            Importer l'historique de {c.nom}
          </Button>
        </Stack>
      ) : (
        <Stack gap="md">
          {!c.dividendes && (
            <Alert variant="light" color="ambre" radius="md" p="xs" icon={<IconInfoCircle size={16} />}>
              <Text fz="xs">Indice hors dividendes : il oublie les 3 à 4 % par an de dividendes de ses sociétés, alors que ton compte les compte. La comparaison te flatte.</Text>
            </Alert>
          )}
          <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="md">
            <Colonne titre="Ton compte Bourse" valeur={c.toi.valeur} rendement={c.toi.rendement} />
            <Colonne titre={`Dans ${c.nom}`} valeur={c.reference!.valeur} rendement={c.reference!.rendement} />
            <Box>
              <Text fz="xs" c="dimmed">Écart</Text>
              <Text className="chiffre" fz={20} fw={700} c={signe(c.ecart!)}>{(c.ecart! >= 0 ? '+' : '−') + fmt(Math.abs(c.ecart!))}</Text>
              <Text fz="sm" c="dimmed">{c.ecart! >= 0 ? "d'avance sur l'indice" : "de retard sur l'indice"}</Text>
            </Box>
          </SimpleGrid>
          {points.length >= 2 && (
            <Graphique type="line" hauteur={220} options={{
              ...base,
              plugins: { legend: { position: 'top', align: 'end' }, tooltip: { callbacks: {
                title: items => items.length ? dateFr(points[items[0].dataIndex].date) : '',
                label: ctx => `${ctx.dataset.label} : ${fmt(ctx.parsed.y ?? 0)}`,
              } } },
            }} data={{
              labels: points.map(p => format(p.date)),
              datasets: [
                { label: 'Ton compte', data: points.map(p => p.toi), borderColor: C.ep, backgroundColor: C.ep, tension: .2, pointRadius: 0 },
                { label: c.nom, data: points.map(p => p.indice), borderColor: C.rev, backgroundColor: C.rev, borderDash: [5, 4], tension: .2, pointRadius: 0 },
              ],
            } as ChartData} />
          )}
          <Text fz="xs" c="dimmed">
            Valeur de l'indice au {dateFr(c.date_valeur!)}.
            {c.debut_cours && points.length && points[0].date < c.debut_cours
              ? ` Avant le ${dateFr(c.debut_cours)}, tes titres sont estimés au prix de leur dernière transaction (pas de cours de clôture noté).` : ''}
            {' '}L'indice n'a pas de frais : un fonds indiciel réel ferait un peu moins bien.
          </Text>
        </Stack>
      )}
    </Carte>
  );
}

/* ---------- Paramètres : indices suivis ---------- */
export function IndicesSuivis() {
  const { data, isPending } = useIndices();
  const ecrire = useEcriture('bourse');
  return (
    <Carte titre="Indices de référence" icone={<Pastille icone={IconChartArrowsVertical} couleur="marque" />}
           description="Notés chaque soir de bourse ; importe leurs valeurs passées pour couvrir tes premiers apports">
      {isPending || !data ? <Chargement lignes={3} /> : (
        <Tableau minWidth={520}>
          <Table.Thead>
            <Table.Tr><Table.Th>Indice</Table.Th><Table.Th>Valeurs connues</Table.Th><Table.Th className="num">Dernière</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.indices.map(i => {
              const couvre = !data.premier_mouvement || (!!i.debut && i.debut <= data.premier_mouvement);
              return (
                <Table.Tr key={i.code}>
                  <Table.Td>
                    <Text fz="sm" fw={600}>{i.nom}</Text>
                    <Badge size="xs" variant="light" color={i.dividendes ? 'emeraude' : 'gray'} tt="none">{i.dividendes ? 'dividendes compris' : 'hors dividendes'}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text fz="sm">{i.nb ? `${i.nb} · du ${dateFr(i.debut!)} au ${dateFr(i.fin!)}` : 'aucune'}</Text>
                    {i.nb_import > 0 && <Text fz="xs" c="dimmed">dont {i.nb_import} importées</Text>}
                    {!couvre && <Text fz="xs" c="ambre">ne couvre pas ton premier apport ({dateFr(data.premier_mouvement!)})</Text>}
                  </Table.Td>
                  <Table.Td className="num chiffre">{i.derniere === null ? '—' : i.derniere.toLocaleString('fr-FR')}</Table.Td>
                  <Table.Td>
                    <Group gap={0} wrap="nowrap" justify="flex-end">
                      <Tooltip label="Importer un historique" withArrow>
                        <Button size="compact-xs" variant="subtle" onClick={() => ouvrirImportIndice(i.code)}>Importer</Button>
                      </Tooltip>
                      {i.nb_import > 0 && (
                        <BoutonSuppr label="Retirer les valeurs importées" onClick={() => confirmer(
                          `Retirer les ${i.nb_import} valeurs importées de ${i.nom} ? Celles notées chaque soir restent.`,
                          () => ecrire.mutate({ path: `/api/bourse/indices/${i.code}/import`, method: 'DELETE', succes: 'Valeurs importées retirées' }), 'Retirer')} />
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Tableau>
      )}
    </Carte>
  );
}
