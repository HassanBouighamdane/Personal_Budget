import { useEffect, useState } from 'react';
import { ActionIcon, Badge, Box, Button, Checkbox, Divider, Grid, Group, NumberInput, PasswordInput, SegmentedControl, Stack, Table, Text, TextInput, Tooltip } from '@mantine/core';
import { MonthPickerInput } from '@mantine/dates';
import { modals } from '@mantine/modals';
import { IconBell, IconBriefcase, IconCategory, IconDeviceFloppy, IconEye, IconHistory, IconLock, IconPlus, IconSend, IconTarget } from '@tabler/icons-react';

import { api, toast } from '../lib/api';
import { auj, fmt, libelleMois } from '../lib/format';
import type { Categorie, Source } from '../lib/types';
import { useApercuRappels, useConfig, useEcriture, useEtatRappels, useHistoriqueBudget } from '../lib/queries';
import { ImportExport } from '../components/ImportExport';
import { BoutonSuppr, Carte, Chargement, confirmer, EnTetePage, Info, Pastille, Tableau, Vide } from '../components/ui';

const nombre = (v: string | number) => (typeof v === 'number' ? v : parseFloat(v)) || 0;

function BoutonSauver({ modifie, onClick, loading }: { modifie: boolean; onClick: () => void; loading: boolean }) {
  return (
    <Tooltip label="Enregistrer" withArrow>
      <ActionIcon variant={modifie ? 'filled' : 'default'} size="lg" onClick={onClick} loading={loading} aria-label="Enregistrer">
        <IconDeviceFloppy size={16} />
      </ActionIcon>
    </Tooltip>
  );
}

const AIDE_FIXE = 'Charge fixe (loyer, factures) : payée une fois par mois, elle ne compte pas dans le budget journalier '
  + 'et hebdomadaire, et la projection de fin de mois la compte pour son budget au lieu de l’extrapoler';

function CaseFixe({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <Tooltip label={AIDE_FIXE} multiline w={280} withArrow>
      <Checkbox label="Fixe" checked={checked} onChange={e => onChange(e.currentTarget.checked)} style={{ flexShrink: 0 }} />
    </Tooltip>
  );
}

/** Budgets successifs d'une catégorie ; retirer un changement rétablit le budget précédent */
function HistoriqueBudget({ c }: { c: Categorie }) {
  const { data, isPending } = useHistoriqueBudget(c.id);
  const ecrire = useEcriture('budget');
  if (isPending) return <Chargement lignes={3} />;
  return (
    <Tableau>
      <Table.Thead>
        <Table.Tr><Table.Th>À partir de</Table.Th><Table.Th className="num">Budget</Table.Th><Table.Th /><Table.Th /></Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {data?.map(h => (
          <Table.Tr key={h.mois_debut}>
            <Table.Td>{h.mois_debut === '1900-01' ? 'Toujours' : libelleMois(h.mois_debut)}</Table.Td>
            <Table.Td className="num chiffre">{fmt(h.budget)}</Table.Td>
            <Table.Td>{h.fixe && <Badge size="xs" variant="light" color="gray">fixe</Badge>}</Table.Td>
            <Table.Td style={{ width: 40 }}>
              {data.length > 1 && <BoutonSuppr label="Retirer ce changement" onClick={() =>
                ecrire.mutate({ path: `/api/categories/${c.id}/historique/${h.mois_debut}`, method: 'DELETE', succes: 'Changement retiré' })} />}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Tableau>
  );
}

function LigneCategorie({ c, aPartirDe }: { c: Categorie; aPartirDe: string }) {
  const ecrire = useEcriture('budget');
  const [nom, setNom] = useState(c.nom);
  const [budget, setBudget] = useState<string | number>(c.budget);
  const [fixe, setFixe] = useState(c.fixe);
  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 2 }} aria-label="Nom" />
      <NumberInput value={budget} onChange={setBudget} min={0} allowNegative={false} decimalSeparator="," thousandSeparator=" "
                   style={{ flex: 1 }} rightSection="DH" aria-label="Budget mensuel" />
      <CaseFixe checked={fixe} onChange={setFixe} />
      <BoutonSauver modifie={nom !== c.nom || nombre(budget) !== c.budget || fixe !== c.fixe} loading={ecrire.isPending}
        onClick={() => ecrire.mutate({ path: '/api/categories/' + c.id, method: 'PUT', body: { nom, budget: nombre(budget), fixe, a_partir_de: aPartirDe },
                                       succes: 'Catégorie mise à jour ✓' })} />
      <Tooltip label="Historique du budget" withArrow>
        <ActionIcon variant="subtle" color="gray" aria-label="Historique du budget" onClick={() => modals.open({
          title: <Text fw={650}>Budget de « {c.nom} »</Text>, centered: true, children: <HistoriqueBudget c={c} />,
        })}>
          <IconHistory size={16} stroke={1.7} />
        </ActionIcon>
      </Tooltip>
      <BoutonSuppr label="Désactiver" onClick={() => confirmer('Désactiver cette catégorie ? (les dépenses existantes sont conservées)',
        () => ecrire.mutate({ path: '/api/categories/' + c.id, method: 'DELETE', succes: 'Catégorie désactivée' }), 'Désactiver')} />
    </Group>
  );
}

function LigneSource({ s }: { s: Source }) {
  const ecrire = useEcriture('budget');
  const [nom, setNom] = useState(s.nom);
  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 1 }} aria-label="Nom de la source" />
      <BoutonSauver modifie={nom !== s.nom} loading={ecrire.isPending}
        onClick={() => ecrire.mutate({ path: '/api/sources/' + s.id, method: 'PUT', body: { nom }, succes: 'Source mise à jour ✓' })} />
      <BoutonSuppr label="Retirer" onClick={() => confirmer('Retirer cette source de la liste ? (les revenus existants sont conservés)',
        () => ecrire.mutate({ path: '/api/sources/' + s.id, method: 'DELETE', succes: 'Source retirée' }), 'Retirer')} />
    </Group>
  );
}

type Periode = 'semaine' | 'mois' | 'annee';

/** Résumé de la dernière semaine ou bilan du dernier mois, tel qu'il part, avec son envoi immédiat */
function ApercuRappels({ peutEnvoyer }: { peutEnvoyer: boolean }) {
  const [periode, setPeriode] = useState<Periode>('semaine');
  const { data, isPending } = useApercuRappels(periode);
  const [envoi, setEnvoi] = useState(false);

  async function envoyer() {
    setEnvoi(true);
    try {
      const r = await api<{ canaux: string[] }>('/api/rappels/envoyer?periode=' + periode, { method: 'POST' });
      toast('Envoyé (' + r.canaux.join(', ') + ') ✓');
    } catch { /* message déjà affiché */ } finally { setEnvoi(false); }
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" gap="xs">
        <SegmentedControl size="xs" value={periode} onChange={v => setPeriode(v as Periode)}
                          data={[{ value: 'semaine', label: 'Semaine' }, { value: 'mois', label: 'Mois' }, { value: 'annee', label: 'Année' }]} />
        <Tooltip label="Configure d'abord Telegram ou l'e-mail" disabled={peutEnvoyer} withArrow>
          <Button size="xs" leftSection={<IconSend size={14} />} onClick={envoyer} loading={envoi} disabled={!peutEnvoyer}>
            Envoyer maintenant
          </Button>
        </Tooltip>
      </Group>
      {isPending || !data ? <Chargement lignes={6} /> : (
        <>
          {data.rappels && (
            <Box>
              <Text fz="xs" fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={4}>Rappels du jour</Text>
              <Text fz="sm" style={{ whiteSpace: 'pre-wrap' }}>{data.rappels}</Text>
            </Box>
          )}
          <Box>
            <Text fz="sm" fw={650} mb={6}>{data.sujet}</Text>
            {/* L'e-mail lui-même, isolé de l'application (aucun script, styles à part) */}
            <iframe title="Aperçu du résumé" srcDoc={data.html} sandbox=""
                    style={{ width: '100%', height: '60vh', border: 0, borderRadius: 12, background: '#f3f4f6', display: 'block' }} />
            <Text fz="xs" c="dimmed" mt={6}>
              Envoyé {periode === 'semaine' ? 'chaque lundi' : periode === 'mois' ? 'le 1er de chaque mois' : 'le 1er janvier'}.
              Sur Telegram, le même contenu arrive sous forme de message.
            </Text>
          </Box>
        </>
      )}
    </Stack>
  );
}

function CarteRappels() {
  const { data: etat, isPending } = useEtatRappels();
  const actif = (c: 'telegram' | 'email') => !!etat?.canaux.includes(c);
  const Etat = ({ ok, children }: { ok: boolean; children: string }) =>
    <Badge variant="light" color={ok ? 'emeraude' : 'gray'}>{children} : {ok ? 'activé' : 'non configuré'}</Badge>;

  return (
    <Carte titre="Rappels et résumés" description="Par Telegram ou e-mail : les échéances le matin, la semaine le lundi, le mois le 1er, l'année le 1er janvier"
           icone={<Pastille icone={IconBell} couleur="ambre" />}>
      {isPending ? <Chargement lignes={2} /> : (
        <Stack gap="sm">
          <Group gap={6}>
            <Etat ok={actif('telegram')}>Telegram</Etat>
            <Etat ok={actif('email')}>E-mail</Etat>
            <Etat ok={!!etat?.cron}>Envoi automatique</Etat>
          </Group>
          {(!etat?.canaux.length || !etat.cron) && (
            <Info>
              Ces réglages sont des variables d'environnement du serveur (jeton Telegram ou compte SMTP, et CRON_SECRET pour
              l'envoi automatique) : la marche à suivre est dans DOCUMENTATION.md, section « Carnet, rappels et résumés ».
            </Info>
          )}
          <Button variant="default" leftSection={<IconEye size={16} />} style={{ alignSelf: 'flex-start' }} onClick={() => modals.open({
            title: <Text fw={650}>Aperçu et envoi</Text>, centered: true, size: 'lg', children: <ApercuRappels peutEnvoyer={!!etat?.canaux.length} />,
          })}>Aperçu et envoi</Button>
        </Stack>
      )}
    </Carte>
  );
}

export function Parametres({ onMdpChange }: { onMdpChange: () => void }) {
  const { data: config, isPending } = useConfig();
  const ecrire = useEcriture('budget');
  const [objectif, setObjectif] = useState<string | number>('');
  const [nouvCat, setNouvCat] = useState('');
  const [nouvBudget, setNouvBudget] = useState<string | number>('');
  const [nouvFixe, setNouvFixe] = useState(false);
  // Mois à partir duquel un changement de budget s'applique (les mois antérieurs gardent l'ancien)
  const [aPartirDe, setAPartirDe] = useState(auj().slice(0, 7));
  const [nouvSource, setNouvSource] = useState('');
  const [mdpActuel, setMdpActuel] = useState('');
  const [mdpNouveau, setMdpNouveau] = useState('');
  const [envoiMdp, setEnvoiMdp] = useState(false);

  useEffect(() => { if (config) setObjectif(config.objectif_epargne); }, [config?.objectif_epargne]);

  function ajouterCategorie() {
    const nom = nouvCat.trim();
    if (!nom) return toast('Nom requis', false);
    ecrire.mutate({ path: '/api/categories', method: 'POST', body: { nom, budget: nombre(nouvBudget), fixe: nouvFixe, a_partir_de: aPartirDe }, succes: 'Catégorie ajoutée ✓' },
      { onSuccess: () => { setNouvCat(''); setNouvBudget(''); setNouvFixe(false); } });
  }

  function ajouterSource() {
    const nom = nouvSource.trim();
    if (!nom) return toast('Nom requis', false);
    ecrire.mutate({ path: '/api/sources', method: 'POST', body: { nom }, succes: 'Source ajoutée ✓' },
      { onSuccess: () => setNouvSource('') });
  }

  async function changerMdp() {
    if (mdpNouveau.length < 6) return toast('6 caractères minimum', false);
    setEnvoiMdp(true);
    try {
      await api('/api/mot_de_passe', { method: 'PUT', body: { actuel: mdpActuel, nouveau: mdpNouveau } });
    } catch {
      setEnvoiMdp(false);
      return;
    }
    setMdpActuel(''); setMdpNouveau(''); setEnvoiMdp(false);
    toast('Mot de passe changé — reconnecte-toi ✓');
    onMdpChange();
  }

  const objectifCarte = (
      <Carte titre="Objectif d'épargne mensuel" description="Sert à colorer l'épargne et à compter les mois réussis" icone={<Pastille icone={IconTarget} couleur="emeraude" />}>
        <Group gap="xs" wrap="nowrap">
          <NumberInput value={objectif} onChange={setObjectif} min={0} allowNegative={false} decimalSeparator="," thousandSeparator=" "
                       rightSection="DH" style={{ flex: 1 }} aria-label="Objectif d'épargne mensuel" />
          <Button loading={ecrire.isPending}
            onClick={() => ecrire.mutate({ path: '/api/objectif', method: 'PUT', body: { objectif: nombre(objectif) }, succes: 'Objectif enregistré ✓' })}>
            Enregistrer
          </Button>
        </Group>
      </Carte>
  );

  const categoriesCarte = (
      <Carte titre="Catégories et budgets mensuels" description="Budget en DH par mois ; « Fixe » pour le loyer et les factures ; désactiver garde les dépenses existantes" icone={<Pastille icone={IconCategory} couleur="marque" />}>
        <Group gap="xs" mb="sm" wrap="wrap" align="center">
          <Text fz="sm" c="dimmed">Les changements de budget s'appliquent à partir de</Text>
          <MonthPickerInput size="xs" w={150} value={aPartirDe + '-01'} onChange={v => v && setAPartirDe(v.slice(0, 7))}
                            valueFormat="MMMM YYYY" aria-label="Mois à partir duquel le budget s'applique" />
        </Group>
        {isPending ? <Chargement /> : (
          <Stack gap="xs">
            {/* key incluant les valeurs : la ligne se réinitialise après un rechargement */}
            {config?.categories.map(c => <LigneCategorie key={`${c.id}|${c.nom}|${c.budget}|${c.fixe}`} c={c} aPartirDe={aPartirDe} />)}
          </Stack>
        )}
        <Info>Les mois antérieurs gardent leur budget : le « prévu » du passé n'est pas réécrit.</Info>
        <Divider my="md" color="var(--bordure-douce)" />
        <Text fz="xs" fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={8}>Ajouter une catégorie</Text>
        <Group gap="xs" wrap="nowrap">
          <TextInput placeholder="Nom" value={nouvCat} onChange={e => setNouvCat(e.currentTarget.value)} style={{ flex: 2 }} />
          <NumberInput placeholder="Budget" value={nouvBudget} onChange={setNouvBudget} min={0} allowNegative={false}
                       decimalSeparator="," thousandSeparator=" " style={{ flex: 1 }} rightSection="DH" />
          <CaseFixe checked={nouvFixe} onChange={setNouvFixe} />
          <ActionIcon size={36} onClick={ajouterCategorie} aria-label="Ajouter la catégorie"><IconPlus size={18} /></ActionIcon>
        </Group>
      </Carte>
  );

  const sourcesCarte = (
      <Carte titre="Sources de revenus" description="Proposées dans le formulaire de revenu" icone={<Pastille icone={IconBriefcase} couleur="bleu" />}>
        {isPending ? <Chargement /> : !config?.sources.length ? <Vide>Aucune source configurée</Vide> : (
          <Stack gap="xs">
            {config.sources.map(s => <LigneSource key={`${s.id}|${s.nom}`} s={s} />)}
          </Stack>
        )}
        <Divider my="md" color="var(--bordure-douce)" />
        <Text fz="xs" fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={8}>Ajouter une source</Text>
        <Group gap="xs" wrap="nowrap">
          <TextInput placeholder="ex : Loyer perçu" value={nouvSource} onChange={e => setNouvSource(e.currentTarget.value)} style={{ flex: 1 }} />
          <ActionIcon size={36} onClick={ajouterSource} aria-label="Ajouter la source"><IconPlus size={18} /></ActionIcon>
        </Group>
      </Carte>
  );

  const mdpCarte = (
      <Carte titre="Changer le mot de passe" description="Tu devras te reconnecter ensuite" icone={<Pastille icone={IconLock} couleur="gray" />}>
        <Stack gap="sm">
          <PasswordInput label="Mot de passe actuel" autoComplete="current-password"
                         value={mdpActuel} onChange={e => setMdpActuel(e.currentTarget.value)} />
          <PasswordInput label="Nouveau mot de passe (6 caractères min.)" autoComplete="new-password"
                         value={mdpNouveau} onChange={e => setMdpNouveau(e.currentTarget.value)} />
          <Button onClick={changerMdp} loading={envoiMdp} style={{ alignSelf: 'flex-start' }}>Mettre à jour</Button>
        </Stack>
      </Carte>
  );

  return (
    <Stack gap="lg">
      <EnTetePage titre="Paramètres" description="Budget, sources de revenus, rappels et sécurité du compte" />
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 7 }}><Stack gap="lg">{categoriesCarte}{sourcesCarte}</Stack></Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}><Stack gap="lg">{objectifCarte}<CarteRappels />{mdpCarte}</Stack></Grid.Col>
        <Grid.Col span={12}><ImportExport /></Grid.Col>
      </Grid>
    </Stack>
  );
}
