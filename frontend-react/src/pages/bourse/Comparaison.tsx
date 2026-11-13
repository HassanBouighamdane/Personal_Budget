/* Bourse — comparaison avec un indice : le compte Bourse face au même argent (mêmes apports, mêmes dates) placé dans l'indice.
 * Les versions « Rentabilité Net » réinvestissent les dividendes : ce sont elles qui se comparent honnêtement au compte.
 * Import des valeurs passées d'un indice (fichier CSV), pour couvrir les apports antérieurs à l'historique. */
import { useState } from 'react';
import { Alert, Badge, Box, Button, Group, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Tooltip } from '@mantine/core';
import { IconChartArrowsVertical, IconFileImport, IconInfoCircle } from '@tabler/icons-react';
import type { ChartData } from 'chart.js';

import { dateFr, fmt, jjmm, jjmmaa } from '../../lib/format';
import { C, signe } from '../../lib/palette';
import type { Indices, IndiceSuivi, ModeComparaison } from '../../lib/types';
import { useComparaison, useEcriture, useIndices } from '../../lib/queries';
import { Graphique, optionsSeries } from '../../components/Graphique';
import { ouvrirImportSerie } from '../../components/ImportSerie';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Tableau } from '../../components/ui';

const pct = (v: number) => (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(1).replace('.', ',') + ' %';
const libelleIndice = (i: Pick<IndiceSuivi, 'nom' | 'dividendes'>) => i.nom + (i.dividendes ? '' : ' (hors dividendes)');

/* ---------- Import d'un historique ---------- */
export function ouvrirImportIndice(code: string, indices: Indices) {
  ouvrirImportSerie({
    titreFenetre: "Importer l'historique d'un indice", titre: 'Indice', module: 'bourse', initial: code,
    series: indices.indices.map(i => ({ value: i.code, label: libelleIndice(i) })),
    chemin: c => `/api/bourse/indices/${c}/import`,
    debutConseille: () => indices.premier_mouvement,
    aide: <>Les valeurs passées de l'indice couvrent tes apports d'avant le début de l'historique. Il faut un fichier de valeurs de
      clôture (journalières, ou au moins une par mois) depuis ton premier apport{indices.premier_mouvement ? `, le ${dateFr(indices.premier_mouvement)}` : ''}.</>,
    avertissement: c => {
      const i = indices.indices.find(x => x.code === c);
      return i && !i.dividendes
        ? <Text fz="xs" c="dimmed">Vérifie que le fichier est bien celui de « {i.nom} » et non de sa version Rentabilité : leurs valeurs n'ont rien à voir.</Text>
        : null;
    },
  });
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
  const [mode, setMode] = useState<ModeComparaison>('compte');
  const actif = code ?? indices?.defaut ?? 'MASRN';
  const { data: c, isPending } = useComparaison(actif, mode);
  const titres = mode === 'titres';
  const choix = (
    <Group gap="xs" wrap="wrap">
      <SegmentedControl size="xs" value={mode} onChange={v => setMode(v as ModeComparaison)} aria-label="Ce qui est comparé"
                        data={[{ value: 'compte', label: 'Tout le compte' }, { value: 'titres', label: 'Choix des titres' }]} />
      <Select size="xs" w={240} data={(indices?.indices ?? []).map(i => ({ value: i.code, label: libelleIndice(i) }))} value={actif}
              onChange={v => v && setCode(v)} allowDeselect={false} aria-label="Indice de référence" comboboxProps={{ withinPortal: true }} />
    </Group>
  );
  const points = c?.points ?? [];
  const format = points.length && points[0].date.slice(0, 4) !== points.at(-1)!.date.slice(0, 4) ? jjmmaa : jjmm;
  const base = optionsSeries();

  return (
    <Carte titre="Comparaison avec l'indice" icone={<Pastille icone={IconChartArrowsVertical} couleur="marque" />} droite={choix}
           description={titres
             ? "Chaque achat de titre placé le même jour dans l'indice, chaque vente et dividende repris : tes titres contre l'indice, sans les espèces"
             : "Tes apports et retraits, aux mêmes dates, placés dans l'indice : tout le compte, espèces comprises"}>
      {isPending || !c ? <Chargement lignes={3} /> : c.etat === 'sans_apport' ? (
        <Info>{titres
          ? "Aucun achat de titre pour l'instant : la comparaison place chaque achat dans l'indice."
          : "Saisis tes apports au compte Bourse (onglet Mouvements) : la comparaison place les mêmes sommes dans l'indice."}</Info>
      ) : c.etat !== 'ok' ? (
        <Stack gap="sm">
          <Info>
            {c.etat === 'vide'
              ? <>Aucune valeur de {c.nom} pour l'instant : elle est notée chaque soir de bourse à partir d'aujourd'hui.</>
              : <>Ton premier {titres ? 'achat' : 'apport'} date du {dateFr(c.manque_avant!)}, avant les valeurs connues de {c.nom}.</>}
            {' '}Importe son historique depuis ce jour-là pour comparer {titres ? 'tous tes achats' : 'tout ton compte'}.
          </Info>
          <Button variant="light" leftSection={<IconFileImport size={16} />} onClick={() => indices && ouvrirImportIndice(c.indice, indices)} style={{ alignSelf: 'flex-start' }}>
            Importer l'historique de {c.nom}
          </Button>
        </Stack>
      ) : (
        <Stack gap="md">
          {!c.dividendes && (
            <Alert variant="light" color="ambre" radius="md" p="xs" icon={<IconInfoCircle size={16} />}>
              <Text fz="xs">Indice hors dividendes : il oublie les 3 à 4 % par an de dividendes de ses sociétés, alors que {titres ? 'tes titres les comptent' : 'ton compte les compte'}. La comparaison te flatte.</Text>
            </Alert>
          )}
          <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="md">
            <Colonne titre={titres ? 'Tes titres (valeur de marché)' : 'Ton compte Bourse'} valeur={c.toi.valeur} rendement={c.toi.rendement} />
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
                { label: titres ? 'Tes titres' : 'Ton compte', data: points.map(p => p.toi), borderColor: C.ep, backgroundColor: C.ep, tension: .2, pointRadius: 0 },
                { label: c.nom, data: points.map(p => p.indice), borderColor: C.rev, backgroundColor: C.rev, borderDash: [5, 4], tension: .2, pointRadius: 0 },
              ],
            } as ChartData} />
          )}
          <Text fz="xs" c="dimmed">
            Valeur de l'indice au {dateFr(c.date_valeur!)}.
            {c.debut_cours && points.length && points[0].date < c.debut_cours
              ? ` Avant le ${dateFr(c.debut_cours)}, tes titres sont estimés au prix de leur dernière transaction (pas de cours de clôture noté).` : ''}
            {titres ? " Les ventes et les dividendes sortent des deux côtés : les espèces qui attendent ne comptent pas." : ''}
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
                        <Button size="compact-xs" variant="subtle" onClick={() => ouvrirImportIndice(i.code, data)}>Importer</Button>
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
