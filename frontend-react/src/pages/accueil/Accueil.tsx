/* Accueil — l'essentiel du jour, tiré de chaque module : ce qu'il reste à dépenser, la Bourse, la lecture
 * en cours, la note du jour et ce qui demande une action. Chaque bloc mène à son écran. */
import type { ReactNode } from 'react';
import { Badge, Box, Button, Grid, Group, Progress, SimpleGrid, Stack, Text } from '@mantine/core';
import {
  IconArrowRight, IconBook2, IconBuildingBank, IconCalendarDue, IconCheck, IconFlame, IconPencilPlus, IconTrendingUp, IconWallet,
} from '@tabler/icons-react';

import { auj, dateFr, fmt, libelleMois } from '../../lib/format';
import { T, signe } from '../../lib/palette';
import {
  useALire, useDettes, useEcheances, usePatrimoineSilencieux, useResumeBourseSilencieux, useResumeJour, useResumeMois, useSerieLecture,
} from '../../lib/queries';
import { Carte, Chargement, EnTetePage, Kpi, Pastille } from '../../components/ui';
import { FenetreNoteDuJour, NoteDuJour } from '../lectures/communs';

/** Écran ouvert depuis l'accueil */
export type CibleAccueil = 'saisie' | 'dash' | 'bourse' | 'lectures' | 'echeances' | 'dettes' | 'patrimoine';

const fmtSigne = (v: number) => (v >= 0 ? '+' : '−') + fmt(Math.abs(v));

function Lien({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <Button variant="subtle" size="compact-sm" rightSection={<IconArrowRight size={14} />} onClick={onClick}>{children}</Button>
  );
}

function delai(jours: number): string {
  if (jours < 0) return `en retard de ${-jours} j`;
  if (jours === 0) return "aujourd'hui";
  if (jours === 1) return 'demain';
  return `dans ${jours} j`;
}

/* ---------- Ce mois-ci ---------- */
function CarteMois({ aller }: { aller: (c: CibleAccueil) => void }) {
  const mois = auj().slice(0, 7);
  const { data: m, isPending } = useResumeMois(mois);
  const part = m?.budget_total ? m.total_depenses / m.budget_total * 100 : 0;
  const depasse = !!m?.projection_fin_mois && !!m.budget_total && m.projection_fin_mois > m.budget_total;
  return (
    <Carte titre={libelleMois(mois)} icone={<Pastille icone={IconWallet} couleur="marque" />} droite={<Lien onClick={() => aller('dash')}>Dashboard</Lien>}>
      {isPending || !m ? <Chargement lignes={2} /> : (
        <Stack gap="xs">
          <Group justify="space-between" align="flex-end" gap="xs">
            <Box>
              <Text fz="xs" c="dimmed">Dépensé</Text>
              <Text className="chiffre" fz={22} fw={700}>{fmt(m.total_depenses)}</Text>
            </Box>
            {m.budget_total > 0 && <Text fz="xs" c="dimmed" ta="right">sur {fmt(m.budget_total)} de budget</Text>}
          </Group>
          {m.budget_total > 0 && <Progress value={Math.min(100, part)} color={part > 100 ? 'rouge' : part > 90 ? 'ambre' : 'marque'} size={8} radius="xl" />}
          <Text fz="xs" c="dimmed">
            {m.total_revenus > 0 && <>Épargne du mois : <Text span inherit fw={600} c={signe(m.epargne)}>{fmtSigne(m.epargne)}</Text>. </>}
            {m.projection_fin_mois ? <>À ce rythme, fin de mois à <Text span inherit fw={600} c={depasse ? T.neg : undefined}>{fmt(m.projection_fin_mois)}</Text>.</> : null}
          </Text>
        </Stack>
      )}
    </Carte>
  );
}

/* ---------- Lecture en cours ---------- */
function CarteLecture({ aller }: { aller: (c: CibleAccueil) => void }) {
  const { data, isPending } = useALire();
  const { data: serie } = useSerieLecture();
  const enCours = (data ?? []).filter(a => a.date_debut);
  return (
    <Carte titre="Lecture en cours" icone={<Pastille icone={IconBook2} couleur="emeraude" />} droite={<Lien onClick={() => aller('lectures')}>Noter ma page</Lien>}>
      {isPending ? <Chargement lignes={2} /> : (
        <Stack gap="sm">
          {!enCours.length && <Text fz="sm" c="dimmed">Aucun livre en cours. Lance-en un depuis ta liste à lire.</Text>}
          {enCours.slice(0, 3).map(a => (
            <Box key={a.id}>
              <Text fz="sm" fw={600} truncate>{a.titre}</Text>
              {a.page_actuelle !== null && a.pages ? (
                <>
                  <Progress value={Math.min(100, a.page_actuelle / a.pages * 100)} color="emeraude" size={6} radius="xl" mt={5} mb={3} />
                  <Text fz="xs" c="dimmed">
                    p. {a.page_actuelle} / {a.pages}{a.fin_estimee ? ` · fin vers le ${dateFr(a.fin_estimee, false)}` : ''}
                  </Text>
                </>
              ) : (
                <Text fz="xs" c="dimmed">{a.page_actuelle !== null ? `p. ${a.page_actuelle}` : `commencé le ${dateFr(a.date_debut!, false)}`}</Text>
              )}
            </Box>
          ))}
          {!!serie && serie.serie > 0 && (
            <Badge variant="light" color={serie.lu_aujourdhui ? 'ambre' : 'gray'} leftSection={<IconFlame size={12} stroke={2} />} style={{ alignSelf: 'flex-start' }}>
              {serie.serie} jour{serie.serie > 1 ? 's' : ''} de suite{serie.lu_aujourdhui ? '' : " · pas encore lu aujourd'hui"}
            </Badge>
          )}
        </Stack>
      )}
    </Carte>
  );
}

/* ---------- À traiter : échéances et remboursements en retard ---------- */
function CarteATraiter({ aller }: { aller: (c: CibleAccueil) => void }) {
  const { data: echeances, isPending } = useEcheances();
  const { data: dettes } = useDettes();
  const aTraiter = (echeances ?? []).filter(e => e.a_rappeler);
  const enRetard = (dettes ?? []).filter(d => d.reste > 0 && d.echeance && d.echeance < auj());
  const rien = !aTraiter.length && !enRetard.length;
  return (
    <Carte titre="À traiter" icone={<Pastille icone={IconCalendarDue} couleur={rien ? 'gray' : 'ambre'} />}
           droite={<Lien onClick={() => aller('echeances')}>Échéances</Lien>}>
      {isPending ? <Chargement lignes={2} /> : rien ? (
        <Group gap="xs"><IconCheck size={16} color="var(--c-ep)" /><Text fz="sm" c="dimmed">Rien d'urgent : aucune échéance proche, aucun remboursement en retard.</Text></Group>
      ) : (
        <Stack gap={8}>
          {aTraiter.slice(0, 5).map(e => (
            <Group key={e.id} justify="space-between" wrap="nowrap" gap="xs">
              <Text fz="sm" truncate>{e.titre}</Text>
              <Badge size="sm" variant="light" color={e.jours_restants < 0 ? 'rouge' : 'ambre'} style={{ flexShrink: 0 }}>{delai(e.jours_restants)}</Badge>
            </Group>
          ))}
          {aTraiter.length > 5 && <Text fz="xs" c="dimmed">et {aTraiter.length - 5} autre{aTraiter.length > 6 ? 's' : ''}</Text>}
          {enRetard.map(d => (
            <Group key={'d' + d.id} justify="space-between" wrap="nowrap" gap="xs" style={{ cursor: 'pointer' }} onClick={() => aller('dettes')}>
              <Text fz="sm" truncate>{d.sens === 'pret' ? `${d.personne} te doit` : `Tu dois à ${d.personne}`} {fmt(d.reste)}</Text>
              <Badge size="sm" variant="light" color="rouge" style={{ flexShrink: 0 }}>échéance dépassée</Badge>
            </Group>
          ))}
        </Stack>
      )}
    </Carte>
  );
}

/* ---------- Page ---------- */
export function Accueil({ utilisateur, aller }: { utilisateur: string; aller: (c: CibleAccueil) => void }) {
  const { data: jour } = useResumeJour(auj());
  const { data: mois } = useResumeMois(auj().slice(0, 7));
  const { data: bourse } = useResumeBourseSilencieux('');
  const { data: patrimoine } = usePatrimoineSilencieux();
  const resteJour = jour ? jour.budget_jour - jour.depenses_variables : null;
  const aBourse = !!bourse && (bourse.patrimoine_total !== 0 || bourse.apports_nets !== 0);
  const heure = new Date().getHours();
  const reserve = patrimoine?.reserve.mois_couverts;

  return (
    <Stack gap="lg">
      <EnTetePage titre={`${heure < 18 ? 'Bonjour' : 'Bonsoir'} ${utilisateur}`}
                  description={new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}
                  actions={<Button leftSection={<IconPencilPlus size={16} />} onClick={() => aller('saisie')}>Ajouter une dépense</Button>} />
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing={{ base: 'xs', sm: 'md' }}>
        <Kpi label="Reste à dépenser aujourd'hui" icone={IconWallet} teinte="marque"
             valeur={resteJour === null ? '…' : fmt(resteJour)} couleur={resteJour === null ? undefined : signe(resteJour)}
             aide={jour ? (jour.budget_jour > 0 ? `${fmt(jour.depenses_variables)} dépensés sur ${fmt(jour.budget_jour)} par jour` : 'aucun budget variable défini') : undefined} />
        <Kpi label="Reste ce mois-ci" icone={IconCalendarDue} teinte="bleu"
             valeur={mois ? fmt(mois.reste_budget) : '…'} couleur={mois ? signe(mois.reste_budget) : undefined}
             aide={mois ? `budget du mois : ${fmt(mois.budget_total)}` : undefined} />
        {aBourse && (
          <Kpi label="Portefeuille Bourse" icone={IconTrendingUp} teinte="emeraude" valeur={fmt(bourse!.patrimoine_total)}
               aide={<>plus-value latente : <Text span inherit fw={600} c={signe(bourse!.plus_value_latente)}>{fmtSigne(bourse!.plus_value_latente)}</Text></>} />
        )}
        {patrimoine && (
          <Kpi label="Patrimoine net" icone={IconBuildingBank} teinte="emeraude" valeur={fmt(patrimoine.total)} couleur={signe(patrimoine.total)}
               aide={reserve != null ? `réserve : ${String(reserve).replace('.', ',')} mois de dépenses` : 'tout ce que tu possèdes'} />
        )}
      </SimpleGrid>
      <NoteDuJour />
      <FenetreNoteDuJour />
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Stack gap="lg">
            <CarteATraiter aller={aller} />
            <CarteMois aller={aller} />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Stack gap="lg">
            <CarteLecture aller={aller} />
            {aBourse && (
              <Carte titre="Bourse" icone={<Pastille icone={IconTrendingUp} couleur="emeraude" />} droite={<Lien onClick={() => aller('bourse')}>Portefeuille</Lien>}>
                <Stack gap={6}>
                  {([['Titres, à leur valeur de marché', fmt(bourse!.valeur_marche), undefined],
                     ['Espèces disponibles', fmt(bourse!.especes_disponibles), undefined],
                     ['Performance globale', `${fmtSigne(bourse!.performance_globale)}${bourse!.apports_nets > 0 ? ` (${(bourse!.performance_globale_pct * 100).toFixed(1).replace('.', ',')} %)` : ''}`,
                      signe(bourse!.performance_globale)]] as const).map(([nom, valeur, couleur]) => (
                    <Group key={nom} justify="space-between" gap="xs" wrap="nowrap">
                      <Text fz="sm" c="dimmed">{nom}</Text>
                      <Text fz="sm" fw={600} className="chiffre" c={couleur} style={{ whiteSpace: 'nowrap' }}>{valeur}</Text>
                    </Group>
                  ))}
                </Stack>
              </Carte>
            )}
            {patrimoine && (
              <Button variant="default" rightSection={<IconArrowRight size={14} />} onClick={() => aller('patrimoine')} style={{ alignSelf: 'flex-start' }}>
                Voir le détail du patrimoine
              </Button>
            )}
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
