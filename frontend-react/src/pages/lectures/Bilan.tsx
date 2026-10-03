/* Lectures — bilan annuel : objectifs, rythme, genres, records et historique */
import type { ReactNode } from 'react';
import { Box, Group, Progress, Rating, Skeleton, Stack, Table, Text } from '@mantine/core';
import type { ChartOptions } from 'chart.js';
import {
  IconBook, IconBooks, IconCalendarCheck, IconCalendarMonth, IconClock, IconFileText, IconStar, IconTarget,
} from '@tabler/icons-react';

import { jjmm, MOIS_FR } from '../../lib/format';
import { C, PALETTE, regrouperAutres, T } from '../../lib/palette';
import type { Livre } from '../../lib/types';
import { useBilanLecture } from '../../lib/queries';
import { Donut, Graphique } from '../../components/Graphique';
import { Carte, Grille2, GrilleKpi, Kpi, Tableau, ThTri, TitreSection, useTri, Variation, Vide } from '../../components/ui';

const LIVRES = PALETTE[0];   // indigo
const pluriel = (n: number, mot: string) => `${n} ${mot}${Math.abs(n) > 1 ? 's' : ''}`;

// Axe des nombres de livres : entiers uniquement
const optionsLivres: ChartOptions = {
  interaction: { mode: 'index', intersect: false },
  plugins: { legend: { position: 'top', align: 'end' } },
  scales: {
    x: { border: { display: false }, grid: { display: false } },
    y: { border: { display: false }, beginAtZero: true, ticks: { precision: 0, maxTicksLimit: 6 } },
  },
};

/** Avance ou retard par rapport à l'objectif annuel, ou résultat final pour une année terminée */
function suiviObjectif(nb: number, objectif: number, attendu: number, courante: boolean) {
  if (!objectif) return { texte: 'aucun objectif annuel défini', couleur: undefined };
  if (!courante) {
    return nb >= objectif
      ? { texte: 'objectif atteint ✓', couleur: T.ep }
      : { texte: `manqué de ${pluriel(objectif - nb, 'livre')}`, couleur: T.neg };
  }
  if (nb >= objectif) return { texte: 'objectif déjà atteint ✓', couleur: T.ep };
  const ecart = Math.round(nb - attendu);
  if (ecart > 0) return { texte: `en avance de ${pluriel(ecart, 'livre')}`, couleur: T.ep };
  if (ecart < 0) return { texte: `${pluriel(-ecart, 'livre')} de retard sur le rythme`, couleur: T.warn };
  return { texte: 'pile dans le rythme', couleur: T.ep };
}

function Record({ titre, livre, valeur }: { titre: string; livre: Livre | null; valeur: (l: Livre) => ReactNode }) {
  return (
    <Box>
      <Text fz={11} fw={700} c="dimmed" tt="uppercase" lts={0.5}>{titre}</Text>
      {livre ? (
        <>
          <Text fw={650} fz="sm" mt={4} lineClamp={2}>{livre.titre}</Text>
          {livre.auteur && <Text fz="xs" c="dimmed">{livre.auteur}</Text>}
          <Box mt={4}>{valeur(livre)}</Box>
        </>
      ) : <Text fz="sm" c="dimmed" mt={4}>—</Text>}
    </Box>
  );
}

function TableLivres({ livres }: { livres: Livre[] }) {
  type Cle = 'date' | 'titre' | 'auteur' | 'genre' | 'pages' | 'note';
  const { triees, tri, basculer } = useTri<Livre, Cle>(livres, (l, c) =>
    c === 'date' ? l.date_fin : c === 'titre' ? l.titre : c === 'auteur' ? l.auteur : c === 'genre' ? l.genre
      : c === 'pages' ? l.pages ?? 0 : l.note ?? 0,
    { cle: 'date', desc: true });
  const th = { tri, basculer };
  return (
    <Tableau minWidth={640}>
      <Table.Thead>
        <Table.Tr>
          <ThTri cle="date" {...th}>Fini le</ThTri><ThTri cle="titre" {...th}>Titre</ThTri><ThTri cle="auteur" {...th}>Auteur</ThTri>
          <ThTri cle="genre" {...th}>Genre</ThTri><ThTri cle="pages" num {...th}>Pages</ThTri><ThTri cle="note" {...th}>Avis</ThTri>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {triees.map(l => (
          <Table.Tr key={l.id}>
            <Table.Td c="dimmed" style={{ whiteSpace: 'nowrap' }}>{jjmm(l.date_fin)}</Table.Td>
            <Table.Td fw={600}>{l.titre}</Table.Td>
            <Table.Td>{l.auteur}</Table.Td>
            <Table.Td c="dimmed" fz="xs">{l.genre}</Table.Td>
            <Table.Td className="num chiffre">{l.pages ?? '—'}</Table.Td>
            <Table.Td>{l.note ? <Rating value={l.note} readOnly size="xs" /> : <Text c="dimmed" fz="xs">—</Text>}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Tableau>
  );
}

export function BilanLecture({ annee }: { annee: number }) {
  const { data: b } = useBilanLecture(annee);
  if (!b) {
    return (
      <>
        <GrilleKpi>{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} h={108} radius="lg" />)}</GrilleKpi>
        <Grille2><Skeleton h={320} radius="lg" /><Skeleton h={320} radius="lg" /></Grille2>
      </>
    );
  }

  const labels = MOIS_FR.map(m => m.slice(0, 4));
  const suivi = suiviObjectif(b.nb_livres, b.objectif_annuel, b.attendu_a_date, b.est_annee_courante);
  const pctObjectif = b.objectif_annuel ? Math.min(b.nb_livres / b.objectif_annuel * 100, 100) : 0;

  // Livres cumulés mois par mois (jusqu'au mois en cours pour l'année courante) vs rythme régulier de l'objectif
  let cumul = 0;
  const cumulMois = b.par_mois.map((x, i) => (i < b.nb_mois_ecoules ? (cumul += x.livres) : null));
  const historique = b.historique.filter(h => h.annee <= Math.max(annee, new Date().getFullYear()));

  return (
    <>
      <TitreSection>Objectifs</TitreSection>
      <GrilleKpi>
        <Kpi label={`Livres lus en ${annee}`} icone={IconBooks} teinte="marque" valeur={b.nb_livres} couleur={T.rev}
             badge={<Variation actuel={b.nb_livres} precedent={b.nb_livres_annee_precedente} inverse />}
             aide={`${annee - 1} : ${pluriel(b.nb_livres_annee_precedente, 'livre')}`} />
        <Kpi label="Objectif annuel" icone={IconTarget} teinte="emeraude"
             valeur={b.objectif_annuel ? `${b.nb_livres} / ${b.objectif_annuel}` : '—'} couleur={suivi.couleur}
             aide={<>
               {b.objectif_annuel > 0 && <Progress value={pctObjectif} color={suivi.couleur ?? 'marque'} size={6} radius="xl" mb={6} />}
               <Text span inherit c={suivi.couleur}>{suivi.texte}</Text>
             </>} />
        {b.livres_mois_courant !== null && (
          <Kpi label={`${MOIS_FR[new Date().getMonth()]} (en cours)`} icone={IconCalendarMonth} teinte="bleu"
               valeur={b.objectif_mensuel ? `${b.livres_mois_courant} / ${b.objectif_mensuel}` : b.livres_mois_courant}
               couleur={b.objectif_mensuel && b.livres_mois_courant >= b.objectif_mensuel ? T.ep : undefined}
               aide={!b.objectif_mensuel ? 'aucun objectif mensuel défini'
                 : b.livres_mois_courant >= b.objectif_mensuel ? 'objectif du mois atteint ✓'
                 : `encore ${pluriel(b.objectif_mensuel - b.livres_mois_courant, 'livre')} ce mois-ci`} />
        )}
        <Kpi label="Mois réussis" icone={IconCalendarCheck} teinte="emeraude"
             valeur={b.objectif_mensuel ? `${b.nb_mois_objectif} / ${b.nb_mois_ecoules}` : '—'}
             aide={b.objectif_mensuel ? `mois à ≥ ${pluriel(b.objectif_mensuel, 'livre')}` : 'aucun objectif mensuel défini'} />
      </GrilleKpi>

      <TitreSection>Lecture</TitreSection>
      <GrilleKpi>
        <Kpi label="Pages lues" icone={IconFileText} teinte="gray" valeur={b.nb_pages.toLocaleString('fr-FR')}
             aide={b.pages_moyennes ? `${b.pages_moyennes} pages / livre en moyenne` : 'renseigne les pages pour ce total'} />
        <Kpi label="Avis moyen" icone={IconStar} teinte="ambre"
             valeur={b.note_moyenne !== null ? `${b.note_moyenne.toLocaleString('fr-FR')} / 5` : '—'}
             aide={b.note_moyenne !== null ? <Rating value={b.note_moyenne} fractions={4} readOnly size="xs" /> : 'aucun livre noté'} />
        <Kpi label="Durée moyenne" icone={IconClock} teinte="gray"
             valeur={b.duree_moyenne_jours !== null ? pluriel(Math.round(b.duree_moyenne_jours), 'jour') : '—'}
             aide={b.duree_moyenne_jours !== null ? 'par livre, du début à la fin' : 'renseigne la date de début'} />
      </GrilleKpi>

      {!b.nb_livres ? (
        <Carte><Vide icone={IconBook}>Aucun livre terminé en {annee}.</Vide></Carte>
      ) : (
        <>
          <Grille2>
            <Carte titre="Livres par mois" description={b.objectif_mensuel ? `Objectif : ${pluriel(b.objectif_mensuel, 'livre')} par mois` : undefined}>
              <Graphique type="bar" options={optionsLivres} data={{
                labels,
                datasets: [
                  {
                    type: 'bar' as const, label: 'Livres', data: b.par_mois.map(x => x.livres), borderRadius: 5,
                    backgroundColor: b.par_mois.map(x => (b.objectif_mensuel && x.livres >= b.objectif_mensuel ? C.ep : LIVRES)),
                  },
                  ...(b.objectif_mensuel ? [{
                    type: 'line' as const, label: 'Objectif mensuel', data: Array(12).fill(b.objectif_mensuel),
                    borderColor: C.budget, borderDash: [6, 4], pointRadius: 0,
                  }] : []),
                ],
              }} />
            </Carte>
            <Carte titre="Progression de l'année" description="Livres cumulés comparés au rythme de l'objectif">
              <Graphique type="line" options={optionsLivres} data={{
                labels,
                datasets: [
                  { label: 'Livres lus', data: cumulMois, borderColor: LIVRES, backgroundColor: 'rgba(99,102,241,.14)', fill: true, tension: .3, pointRadius: 3 },
                  ...(b.objectif_annuel ? [{
                    label: 'Rythme objectif', data: labels.map((_, i) => Math.round(b.objectif_annuel * (i + 1) / 12 * 10) / 10),
                    borderColor: C.budget, borderDash: [6, 4], pointRadius: 0,
                  }] : []),
                ],
              }} />
            </Carte>
          </Grille2>

          <Grille2>
            <Carte titre="Genres" description="Nombre de livres par genre">
              <Donut {...regrouperAutres(b.genres.map(g => g.genre), b.genres.map(g => g.livres))} />
            </Carte>
            <Carte titre="Records de l'année">
              <Stack gap="lg">
                <Group grow align="flex-start" gap="md">
                  <Record titre="Coup de cœur" livre={b.mieux_note} valeur={l => <Rating value={l.note ?? 0} readOnly size="xs" />} />
                  <Record titre="Le plus long" livre={b.plus_long} valeur={l => <Text fz="xs" className="chiffre">{l.pages} pages</Text>} />
                  <Record titre="Le plus court" livre={b.plus_court} valeur={l => <Text fz="xs" className="chiffre">{l.pages} pages</Text>} />
                </Group>
                <Box>
                  <Text fz={11} fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={6}>Auteurs les plus lus</Text>
                  {b.auteurs.length ? (
                    <Stack gap={4}>
                      {b.auteurs.map(a => (
                        <Group key={a.auteur} justify="space-between" wrap="nowrap">
                          <Text fz="sm" truncate>{a.auteur}</Text>
                          <Text fz="sm" fw={600} className="chiffre" style={{ whiteSpace: 'nowrap' }}>{pluriel(a.livres, 'livre')}</Text>
                        </Group>
                      ))}
                    </Stack>
                  ) : <Text fz="sm" c="dimmed">—</Text>}
                </Box>
              </Stack>
            </Carte>
          </Grille2>

          <Carte titre={`Les livres de ${annee}`} description="Clique sur un en-tête de colonne pour trier">
            <TableLivres livres={b.livres} />
          </Carte>
        </>
      )}

      {historique.length > 1 && (
        <Carte titre="Livres lus par année" description="Tout ton historique de lecture">
          <Graphique type="bar" hauteur={240} options={{ ...optionsLivres, plugins: { legend: { display: false } } }} data={{
            labels: historique.map(h => String(h.annee)),
            datasets: [{
              label: 'Livres', data: historique.map(h => h.livres), borderRadius: 5,
              backgroundColor: historique.map(h => (h.annee === annee ? LIVRES : 'rgba(99,102,241,.35)')),
            }],
          }} />
        </Carte>
      )}
    </>
  );
}
