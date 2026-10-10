/* Suivi — dettes et prêts : argent prêté (on me doit) ou emprunté (je dois), remboursé en une ou plusieurs fois.
 * Ce sont des transferts, à ne pas saisir dans le Budget. */
import { useState, type ReactNode } from 'react';
import {
  ActionIcon, Autocomplete, Badge, Box, Button, Grid, Group, Progress, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { modals } from '@mantine/modals';
import { IconArrowDownLeft, IconArrowUpRight, IconCash, IconCheck, IconHeartHandshake, IconPencil, IconScale } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr, fmt, lireMontant } from '../../lib/format';
import { T, signe } from '../../lib/palette';
import type { Dette } from '../../lib/types';
import { useDettes, useEcriture } from '../../lib/queries';
import { ChampDate, ChampMontant } from '../../components/champs';
import { Aide, BoutonSuppr, Carte, Chargement, confirmer, Kpi, Pastille, Vide } from '../../components/ui';

const texte = (n: number) => String(n).replace('.', ',');

function ouvrir(titre: string, contenu: (fermer: () => void) => ReactNode) {
  const id = modals.open({ title: <Text fw={650}>{titre}</Text>, centered: true, children: contenu(() => modals.close(id)) });
}

function FormDette({ existante, onTermine }: { existante?: Dette; onTermine?: () => void }) {
  const ecrire = useEcriture('carnet');
  const { data: dettes } = useDettes();
  const [sens, setSens] = useState<Dette['sens']>(existante?.sens ?? 'pret');
  const [personne, setPersonne] = useState(existante?.personne ?? '');
  const [montant, setMontant] = useState(existante ? texte(existante.montant) : '');
  const [date, setDate] = useState(existante?.date_operation ?? auj());
  const [echeance, setEcheance] = useState<string | null>(existante?.echeance ?? null);
  const [libelle, setLibelle] = useState(existante?.libelle ?? '');
  const personnes = [...new Set((dettes ?? []).map(d => d.personne))].sort((a, b) => a.localeCompare(b, 'fr'));

  function enregistrer() {
    const m = lireMontant(montant);
    if (!personne.trim()) return toast('Indique la personne', false);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    if (echeance && echeance < date) return toast("L'échéance doit suivre la date du prêt", false);
    const body = { sens, personne: personne.trim(), montant: m, date_operation: date, echeance, libelle: libelle.trim() };
    ecrire.mutate(
      existante ? { path: `/api/carnet/dettes/${existante.id}`, method: 'PUT', body, succes: 'Modifié ✓' }
                : { path: '/api/carnet/dettes', method: 'POST', body, succes: sens === 'pret' ? 'Prêt ajouté ✓' : 'Emprunt ajouté ✓' },
      { onSuccess: () => { if (!existante) { setPersonne(''); setMontant(''); setEcheance(null); setLibelle(''); } onTermine?.(); } },
    );
  }

  return (
    <Stack gap="sm">
      <SegmentedControl fullWidth value={sens} onChange={v => setSens(v as Dette['sens'])}
                        data={[{ value: 'pret', label: "J'ai prêté" }, { value: 'emprunt', label: "J'ai emprunté" }]} />
      <Autocomplete label={sens === 'pret' ? 'À qui' : 'À qui je dois'} placeholder="ex : Ahmed" data={personnes}
                    value={personne} onChange={setPersonne} limit={20} />
      <ChampMontant label="Montant" value={montant} onChange={setMontant} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampDate value={date} onChange={setDate} />
        <DatePickerInput label="À rendre avant le" placeholder="Optionnel" value={echeance} onChange={setEcheance} clearable
                         valueFormat="DD/MM/YYYY" minDate={date} popoverProps={{ withinPortal: true }} />
      </SimpleGrid>
      <TextInput label="Motif (optionnel)" placeholder="ex : avance pour le voyage" value={libelle}
                 onChange={e => setLibelle(e.currentTarget.value)} maxLength={200} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{existante ? 'Enregistrer' : 'Ajouter'}</Button>
    </Stack>
  );
}

/** Remboursements d'une dette : liste, suppression et ajout (le reste dû est proposé par défaut) */
function Remboursements({ id }: { id: number }) {
  const { data: dettes } = useDettes();
  const ecrire = useEcriture('carnet');
  const dette = dettes?.find(d => d.id === id);
  const [date, setDate] = useState(auj());
  const [montant, setMontant] = useState('');
  const [libelle, setLibelle] = useState('');
  if (!dette) return <Chargement lignes={2} />;
  const recu = dette.sens === 'pret';

  function enregistrer() {
    // Champ laissé vide : le reste dû, c'est-à-dire un remboursement complet
    const m = montant.trim() ? lireMontant(montant) : dette!.reste;
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate({ path: `/api/carnet/dettes/${id}/remboursements`, method: 'POST',
                    body: { date_operation: date, montant: m, libelle: libelle.trim() },
                    succes: m >= dette!.reste ? 'Soldé ✓' : 'Remboursement ajouté ✓' },
                  { onSuccess: () => { setMontant(''); setLibelle(''); } });
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <Box>
          <Text fz="xs" c="dimmed">{recu ? 'Reste à recevoir' : 'Reste à rendre'}</Text>
          <Text className="chiffre" fz={22} fw={700} c={dette.reste > 0 ? undefined : T.ep}>{fmt(dette.reste)}</Text>
        </Box>
        <Text fz="xs" c="dimmed">{fmt(dette.rembourse)} sur {fmt(dette.montant)}</Text>
      </Group>
      <Progress value={dette.rembourse / dette.montant * 100} color="emeraude" size={8} radius="xl" />
      {dette.remboursements.length > 0 && (
        <Stack gap={2}>
          {dette.remboursements.map(r => (
            <Group key={r.id} className="ligne-op" wrap="nowrap" gap="sm" px={6} py={6}>
              <Text fz="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{dateFr(r.date_operation)}</Text>
              <Text fz="sm" truncate style={{ flex: 1, minWidth: 0 }}>{r.libelle}</Text>
              <Text fz="sm" fw={600} className="chiffre">{fmt(r.montant)}</Text>
              <BoutonSuppr onClick={() => ecrire.mutate({ path: `/api/carnet/remboursements/${r.id}`, method: 'DELETE', succes: 'Remboursement supprimé' })} />
            </Group>
          ))}
        </Stack>
      )}
      {dette.reste > 0 ? (
        <Stack gap="sm">
          <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
            <ChampDate value={date} onChange={setDate} />
            <ChampMontant label="Montant" placeholder={`${texte(dette.reste)} (tout le reste)`} value={montant} onChange={setMontant} />
          </SimpleGrid>
          <TextInput label="Note (optionnel)" placeholder="ex : virement" value={libelle} onChange={e => setLibelle(e.currentTarget.value)} maxLength={200} />
          <Button onClick={enregistrer} loading={ecrire.isPending}>{recu ? 'Enregistrer le remboursement reçu' : 'Enregistrer mon remboursement'}</Button>
        </Stack>
      ) : (
        <Badge variant="light" color="emeraude" leftSection={<IconCheck size={12} stroke={2.4} />} style={{ alignSelf: 'flex-start' }}>Soldé</Badge>
      )}
    </Stack>
  );
}

function LigneDette({ d }: { d: Dette }) {
  const ecrire = useEcriture('carnet');
  const pret = d.sens === 'pret';
  const soldee = d.reste <= 0;
  const enRetard = !soldee && !!d.echeance && d.echeance < auj();
  const details = [d.libelle, `${pret ? 'prêté' : 'emprunté'} le ${dateFr(d.date_operation)}`].filter(Boolean).join(' · ');
  const titre = pret ? `Prêt à ${d.personne}` : `Emprunt auprès de ${d.personne}`;

  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8} align="flex-start">
      <Pastille icone={pret ? IconArrowUpRight : IconArrowDownLeft} couleur={soldee ? 'gray' : pret ? 'emeraude' : 'rose'} taille={34} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text fz="sm" fw={600} truncate>{d.personne}</Text>
          <Text fz="sm" fw={700} className="chiffre" c={soldee ? 'dimmed' : pret ? T.ep : T.dep} style={{ whiteSpace: 'nowrap' }}>
            {fmt(soldee ? d.montant : d.reste)}
          </Text>
        </Group>
        <Text fz="xs" c="dimmed" lineClamp={2}>{details}</Text>
        {!soldee && d.rembourse > 0 && (
          <>
            <Progress value={d.rembourse / d.montant * 100} color="emeraude" size={6} radius="xl" mt={6} />
            <Text fz="xs" c="dimmed" mt={3}>{fmt(d.rembourse)} {pret ? 'reçus' : 'rendus'} sur {fmt(d.montant)}</Text>
          </>
        )}
        {!soldee && d.echeance && (
          <Badge size="xs" variant="light" color={enRetard ? 'rouge' : 'gray'} mt={5}>
            {enRetard ? `dû depuis le ${dateFr(d.echeance, false)}` : `avant le ${dateFr(d.echeance)}`}
          </Badge>
        )}
      </Box>
      <Group gap={0} wrap="nowrap">
        <Tooltip label={soldee ? 'Remboursements' : pret ? 'Remboursement reçu' : "J'ai remboursé"} withArrow>
          <ActionIcon variant="subtle" color={soldee ? 'gray' : 'marque'} aria-label="Remboursements" className={soldee ? 'suppr' : undefined}
                      onClick={() => modals.open({ title: <Text fw={650}>{titre}</Text>, centered: true, children: <Remboursements id={d.id} /> })}>
            <IconCash size={17} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <Tooltip label="Modifier" withArrow>
          <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Modifier"
                      onClick={() => ouvrir('Modifier', fermer => <FormDette existante={d} onTermine={fermer} />)}>
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => confirmer(`Supprimer « ${titre} »${d.remboursements.length ? ' et ses remboursements' : ''} ?`, () =>
          ecrire.mutate({ path: `/api/carnet/dettes/${d.id}`, method: 'DELETE', succes: 'Supprimé' }))} />
      </Group>
    </Group>
  );
}

export function DettesEtPrets() {
  const { data, isPending } = useDettes();
  const [toutes, setToutes] = useState(false);
  const enCours = (data ?? []).filter(d => d.reste > 0);
  const soldees = (data ?? []).filter(d => d.reste <= 0);
  const total = (sens: Dette['sens']) => enCours.filter(d => d.sens === sens).reduce((s, d) => s + d.reste, 0);
  const nb = (sens: Dette['sens']) => enCours.filter(d => d.sens === sens).length;
  const onMeDoit = total('pret'), jeDois = total('emprunt');
  const pluriel = (n: number, mot: string) => `${n} ${mot}${n > 1 ? 's' : ''} en cours`;

  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 2, sm: 3 }} spacing={{ base: 'xs', sm: 'md' }}>
        <Kpi label="On me doit" valeur={fmt(onMeDoit)} couleur={onMeDoit ? T.ep : undefined} aide={pluriel(nb('pret'), 'prêt')}
             icone={IconArrowUpRight} teinte="emeraude" />
        <Kpi label="Je dois" valeur={fmt(jeDois)} couleur={jeDois ? T.dep : undefined} aide={pluriel(nb('emprunt'), 'emprunt')}
             icone={IconArrowDownLeft} teinte="rose" />
        <Kpi label="Solde net" valeur={fmt(onMeDoit - jeDois)} couleur={onMeDoit - jeDois ? signe(onMeDoit - jeDois) : undefined}
             aide="Ce qu'on me doit, moins ce que je dois" icone={IconScale} teinte="marque" />
      </SimpleGrid>
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Carte className="colle" titre="Nouveau prêt ou emprunt" description="Remboursable en une ou plusieurs fois"
                 icone={<Pastille icone={IconHeartHandshake} couleur="marque" />}>
            <FormDette />
          </Carte>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="lg">
            <Carte titre="En cours" description={enCours.length ? 'Les échéances les plus proches en premier' : undefined}>
              {isPending ? <Chargement lignes={3} /> : !enCours.length
                ? <Vide icone={IconHeartHandshake}>Personne ne te doit rien, et tu ne dois rien à personne</Vide>
                : <Stack gap={2}>{enCours.map(d => <LigneDette key={d.id} d={d} />)}</Stack>}
            </Carte>
            {soldees.length > 0 && (
              <Carte titre="Soldés" description={`${soldees.length} prêt${soldees.length > 1 ? 's' : ''} ou emprunt${soldees.length > 1 ? 's' : ''} remboursé${soldees.length > 1 ? 's' : ''}`}
                     droite={soldees.length > 5 && <Button variant="subtle" size="compact-sm" onClick={() => setToutes(t => !t)}>{toutes ? 'Réduire' : 'Tout afficher'}</Button>}>
                <Stack gap={2}>{(toutes ? soldees : soldees.slice(0, 5)).map(d => <LigneDette key={d.id} d={d} />)}</Stack>
              </Carte>
            )}
            <Aide titre="À ne pas saisir dans le Budget">
              Un prêt n'est pas une dépense et son remboursement n'est pas un revenu : c'est de l'argent qui te revient
              (ou que tu dois rendre). Ne le note qu'ici, sinon tes dépenses et ton épargne du mois sont faussées.
            </Aide>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
