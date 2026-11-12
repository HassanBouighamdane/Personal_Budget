/* Accueil — l'essentiel du jour, tiré de chaque module : ce qu'il reste à dépenser, la réserve de sécurité, la Bourse,
 * la lecture en cours, la note du jour et ce qui demande une action. Chaque bloc mène à son écran. */
import type { ReactNode } from 'react';
import { ActionIcon, Badge, Box, Button, Grid, Group, Progress, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core';
import {
  IconAlertTriangle, IconArrowRight, IconBook2, IconBuildingBank, IconCalendarDue, IconCheck, IconChartBar, IconCopy, IconFlame,
  IconPencilPlus, IconScale, IconShieldCheck, IconTarget, IconTrendingUp, IconWallet, IconX,
} from '@tabler/icons-react';

import { auj, dateFr, fmt, libelleMois } from '../../lib/format';
import { T, signe } from '../../lib/palette';
import type { Alerte, EtatRappels, Patrimoine } from '../../lib/types';
import {
  useALire, useAlertes, useDettes, useEcheances, useEcriture, useEtatRappels, useObjectifs, usePatrimoineSilencieux,
  useResumeBourseSilencieux, useResumeJour, useResumeMois, useSerieLecture,
} from '../../lib/queries';
import { Carte, Chargement, EnTetePage, Kpi, Pastille } from '../../components/ui';
import { FenetreNoteDuJour, NoteDuJour } from '../lectures/communs';
import { couleurReserve, Reserve } from '../carnet/Patrimoine';

/** Écran ouvert depuis l'accueil */
export type CibleAccueil = 'saisie' | 'dash' | 'bourse' | 'lectures' | 'echeances' | 'dettes' | 'patrimoine' | 'objectifs' | 'params';

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

/* ---------- Tâche du matin : prévenir quand elle ne tourne plus ---------- */
/** Au-delà, la tâche (appelée vers 8 h chaque matin) a manqué au moins un passage */
const HEURES_SANS_PASSAGE = 36;

/** Problème de la tâche planifiée à signaler, ou null. Rien tant qu'elle n'est pas configurée
 *  (CRON_SECRET) ni tant qu'elle n'a jamais tourné (installation toute neuve). */
export function alerteTache(e: EtatRappels | undefined, maintenant = Date.now()): { titre: string; detail: string } | null {
  if (!e?.cron || !e.passages.length) return null;
  const dernier = e.passages[0];
  const heures = e.dernier_succes ? (maintenant - Date.parse(e.dernier_succes)) / 3.6e6 : Infinity;
  if (heures > HEURES_SANS_PASSAGE) {
    const jours = Math.max(1, Math.round(heures / 24));
    const quand = e.dernier_succes ? `depuis ${jours} jour${jours > 1 ? 's' : ''}` : 'récemment';
    return { titre: `La tâche du matin n'a pas tourné ${quand}`,
             detail: dernier.etat === 'erreur' ? dernier.detail : 'Rappels, résumés et sauvegarde du mois ne partent plus.' };
  }
  if (dernier.etat === 'erreur') return { titre: 'Le dernier passage de la tâche du matin a échoué', detail: dernier.detail };
  return null;
}

/** Rappel de pointer le solde : jamais fait (dès qu'il y a des opérations), ou plus vieux qu'un mois */
export function pointageARefaire(p: Patrimoine | null | undefined): string | null {
  if (!p) return null;
  if (!p.pointage) return p.epargne_cumulee !== 0 ? 'Pointe ton solde : compare tes liquidités à ta banque' : null;
  return p.pointage.a_refaire ? `Pointe ton solde : dernier pointage il y a ${p.pointage.jours} jours` : null;
}

const ICONES_ALERTE = { categorie: IconChartBar, hausse: IconTrendingUp, doublon: IconCopy };

function LigneAlerte({ a }: { a: Alerte }) {
  const ecrire = useEcriture('budget');
  const Icone = ICONES_ALERTE[a.type];
  return (
    <Group justify="space-between" wrap="nowrap" gap="xs" align="flex-start">
      <Group gap={6} wrap="nowrap" align="flex-start" style={{ minWidth: 0 }}>
        <Icone size={15} stroke={1.8} color="var(--c-neg)" style={{ flexShrink: 0, marginTop: 3 }} />
        <Box style={{ minWidth: 0 }}>
          <Text fz="sm" fw={600} truncate>{a.titre}</Text>
          <Text fz="xs" c="dimmed" lineClamp={2}>{a.detail}</Text>
        </Box>
      </Group>
      <Tooltip label="Ignorer cette alerte" withArrow>
        <ActionIcon variant="subtle" color="gray" size="sm" aria-label="Ignorer cette alerte" loading={ecrire.isPending}
                    onClick={() => ecrire.mutate({ path: '/api/alertes/ignorer', method: 'POST', body: { cle: a.cle } })}>
          <IconX size={14} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

/* ---------- À traiter : échéances, remboursements et objectifs en retard, tâche du matin, dépenses inhabituelles ---------- */
function CarteATraiter({ aller }: { aller: (c: CibleAccueil) => void }) {
  const { data: echeances, isPending } = useEcheances();
  const { data: dettes } = useDettes();
  const { data: etatRappels } = useEtatRappels();
  const { data: objectifs } = useObjectifs();
  const { data: alertes } = useAlertes();
  const { data: patrimoine } = usePatrimoineSilencieux();
  const aTraiter = (echeances ?? []).filter(e => e.a_rappeler);
  const enRetard = (dettes ?? []).filter(d => d.reste > 0 && d.echeance && d.echeance < auj());
  const tache = alerteTache(etatRappels);
  const objectifsEnRetard = (objectifs ?? []).filter(o => o.en_retard);
  const enveloppesDepassees = (objectifs ?? []).filter(o => !o.archive && o.depassement > 0);
  const pointage = pointageARefaire(patrimoine);
  const inhabituelles = alertes ?? [];
  const rien = !aTraiter.length && !enRetard.length && !tache && !objectifsEnRetard.length && !enveloppesDepassees.length
    && !pointage && !inhabituelles.length;
  return (
    <Carte titre="À traiter" icone={<Pastille icone={IconCalendarDue} couleur={rien ? 'gray' : 'ambre'} />}
           droite={<Lien onClick={() => aller('echeances')}>Échéances</Lien>}>
      {isPending ? <Chargement lignes={2} /> : rien ? (
        <Group gap="xs"><IconCheck size={16} color="var(--c-ep)" /><Text fz="sm" c="dimmed">Rien d'urgent : aucune échéance proche, aucun remboursement en retard.</Text></Group>
      ) : (
        <Stack gap={8}>
          {tache && (
            <Group justify="space-between" wrap="nowrap" gap="xs" align="flex-start" style={{ cursor: 'pointer' }} onClick={() => aller('params')}>
              <Group gap={6} wrap="nowrap" align="flex-start" style={{ minWidth: 0 }}>
                <IconAlertTriangle size={16} color="var(--c-neg)" style={{ flexShrink: 0, marginTop: 2 }} />
                <Box style={{ minWidth: 0 }}>
                  <Text fz="sm" fw={600}>{tache.titre}</Text>
                  <Text fz="xs" c="dimmed" lineClamp={2}>{tache.detail}</Text>
                </Box>
              </Group>
              <Badge size="sm" variant="light" color="rouge" style={{ flexShrink: 0 }}>Paramètres</Badge>
            </Group>
          )}
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
          {objectifsEnRetard.map(o => (
            <Group key={'o' + o.id} justify="space-between" wrap="nowrap" gap="xs" style={{ cursor: 'pointer' }} onClick={() => aller('objectifs')}>
              <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                <IconTarget size={15} stroke={1.8} style={{ flexShrink: 0 }} />
                <Text fz="sm" truncate>{o.nom} : il manque {fmt(o.reste)}</Text>
              </Group>
              <Badge size="sm" variant="light" color="ambre" style={{ flexShrink: 0 }}>date limite passée</Badge>
            </Group>
          ))}
          {enveloppesDepassees.map(o => (
            <Group key={'e' + o.id} justify="space-between" wrap="nowrap" gap="xs" style={{ cursor: 'pointer' }} onClick={() => aller('objectifs')}>
              <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                <IconTarget size={15} stroke={1.8} style={{ flexShrink: 0 }} />
                <Text fz="sm" truncate>{o.nom} : {fmt(o.depassement)} dépensés au-delà de l'enveloppe</Text>
              </Group>
              <Badge size="sm" variant="light" color="rouge" style={{ flexShrink: 0 }}>enveloppe dépassée</Badge>
            </Group>
          ))}
          {pointage && (
            <Group justify="space-between" wrap="nowrap" gap="xs" style={{ cursor: 'pointer' }} onClick={() => aller('patrimoine')}>
              <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                <IconScale size={15} stroke={1.8} style={{ flexShrink: 0 }} />
                <Text fz="sm" truncate>{pointage}</Text>
              </Group>
              <Badge size="sm" variant="light" color="ambre" style={{ flexShrink: 0 }}>Patrimoine</Badge>
            </Group>
          )}
          {inhabituelles.map(a => <LigneAlerte key={a.cle} a={a} />)}
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
            {/* Toujours visible : couleur de la pastille selon le niveau de la réserve (comme dans Patrimoine) */}
            {patrimoine !== null && (
              <Carte titre="Réserve de sécurité" icone={<Pastille icone={IconShieldCheck} couleur={couleurReserve(reserve ?? null)} />}
                     droite={<Lien onClick={() => aller('patrimoine')}>Patrimoine</Lien>}>
                {patrimoine ? <Reserve p={patrimoine} /> : <Chargement lignes={2} />}
              </Carte>
            )}
            <CarteLecture aller={aller} />
            {aBourse && (
              <Carte titre="Bourse" icone={<Pastille icone={IconTrendingUp} couleur="emeraude" />} droite={<Lien onClick={() => aller('bourse')}>Portefeuille</Lien>}>
                <Stack gap={6}>
                  {([['Titres, à leur valeur de marché', fmt(bourse!.valeur_marche), undefined],
                     ['Espèces disponibles', fmt(bourse!.especes_disponibles), undefined],
                     ['Performance globale', `${fmtSigne(bourse!.performance_globale)}${bourse!.apports_nets > 0 ? ` (${(bourse!.performance_globale_pct * 100).toFixed(1).replace('.', ',')} %)` : ''}`,
                      signe(bourse!.performance_globale)],
                     ...(bourse!.rendement_annualise !== null
                       ? [['Rendement annuel', `${bourse!.rendement_annualise >= 0 ? '+' : '−'}${Math.abs(bourse!.rendement_annualise * 100).toFixed(1).replace('.', ',')} % par an`,
                           signe(bourse!.rendement_annualise)] as const]
                       : [])] as const).map(([nom, valeur, couleur]) => (
                    <Group key={nom} justify="space-between" gap="xs" wrap="nowrap">
                      <Text fz="sm" c="dimmed">{nom}</Text>
                      <Text fz="sm" fw={600} className="chiffre" c={couleur} style={{ whiteSpace: 'nowrap' }}>{valeur}</Text>
                    </Group>
                  ))}
                </Stack>
              </Carte>
            )}
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
