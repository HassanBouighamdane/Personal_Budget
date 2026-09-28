import { useEffect, useState } from 'react';
import { ActionIcon, Button, Group, NumberInput, PasswordInput, Stack, TextInput, Tooltip } from '@mantine/core';
import { IconDeviceFloppy, IconPlus } from '@tabler/icons-react';

import { api, toast } from '../lib/api';
import type { Categorie, Source } from '../lib/types';
import { useConfig, useEcriture } from '../lib/queries';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Vide } from '../components/ui';

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

function LigneCategorie({ c }: { c: Categorie }) {
  const ecrire = useEcriture('budget');
  const [nom, setNom] = useState(c.nom);
  const [budget, setBudget] = useState<string | number>(c.budget);
  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 2 }} aria-label="Nom" />
      <NumberInput value={budget} onChange={setBudget} min={0} allowNegative={false} decimalSeparator="," thousandSeparator=" "
                   style={{ flex: 1 }} rightSection="DH" aria-label="Budget mensuel" />
      <BoutonSauver modifie={nom !== c.nom || nombre(budget) !== c.budget} loading={ecrire.isPending}
        onClick={() => ecrire.mutate({ path: '/api/categories/' + c.id, method: 'PUT', body: { nom, budget: nombre(budget) }, succes: 'Catégorie mise à jour ✓' })} />
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

export function Parametres({ onMdpChange }: { onMdpChange: () => void }) {
  const { data: config, isPending } = useConfig();
  const ecrire = useEcriture('budget');
  const [objectif, setObjectif] = useState<string | number>('');
  const [nouvCat, setNouvCat] = useState('');
  const [nouvBudget, setNouvBudget] = useState<string | number>('');
  const [nouvSource, setNouvSource] = useState('');
  const [mdpActuel, setMdpActuel] = useState('');
  const [mdpNouveau, setMdpNouveau] = useState('');
  const [envoiMdp, setEnvoiMdp] = useState(false);

  useEffect(() => { if (config) setObjectif(config.objectif_epargne); }, [config?.objectif_epargne]);

  function ajouterCategorie() {
    const nom = nouvCat.trim();
    if (!nom) return toast('Nom requis', false);
    ecrire.mutate({ path: '/api/categories', method: 'POST', body: { nom, budget: nombre(nouvBudget) }, succes: 'Catégorie ajoutée ✓' },
      { onSuccess: () => { setNouvCat(''); setNouvBudget(''); } });
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

  return (
    <Stack gap="md">
      <Carte titre="🎯 Objectif d'épargne mensuel">
        <Group gap="xs" wrap="nowrap" maw={420}>
          <NumberInput value={objectif} onChange={setObjectif} min={0} allowNegative={false} decimalSeparator="," thousandSeparator=" "
                       rightSection="DH" style={{ flex: 1 }} aria-label="Objectif d'épargne mensuel" />
          <Button loading={ecrire.isPending}
            onClick={() => ecrire.mutate({ path: '/api/objectif', method: 'PUT', body: { objectif: nombre(objectif) }, succes: 'Objectif enregistré ✓' })}>
            Enregistrer
          </Button>
        </Group>
      </Carte>

      <Carte titre="📂 Catégories et budgets mensuels (DH)">
        {isPending ? <Chargement /> : (
          <Stack gap="xs">
            {/* key incluant les valeurs : la ligne se réinitialise après un rechargement */}
            {config?.categories.map(c => <LigneCategorie key={`${c.id}|${c.nom}|${c.budget}`} c={c} />)}
          </Stack>
        )}
        <Info><b style={{ display: 'block', marginTop: 16, marginBottom: 6 }}>Ajouter une catégorie</b></Info>
        <Group gap="xs" wrap="nowrap">
          <TextInput placeholder="Nom" value={nouvCat} onChange={e => setNouvCat(e.currentTarget.value)} style={{ flex: 2 }} />
          <NumberInput placeholder="Budget" value={nouvBudget} onChange={setNouvBudget} min={0} allowNegative={false}
                       decimalSeparator="," thousandSeparator=" " style={{ flex: 1 }} rightSection="DH" />
          <ActionIcon size="lg" onClick={ajouterCategorie} aria-label="Ajouter la catégorie"><IconPlus size={18} /></ActionIcon>
        </Group>
      </Carte>

      <Carte titre="💼 Sources de revenus">
        {isPending ? <Chargement /> : !config?.sources.length ? <Vide>Aucune source configurée</Vide> : (
          <Stack gap="xs">
            {config.sources.map(s => <LigneSource key={`${s.id}|${s.nom}`} s={s} />)}
          </Stack>
        )}
        <Info><b style={{ display: 'block', marginTop: 16, marginBottom: 6 }}>Ajouter une source</b></Info>
        <Group gap="xs" wrap="nowrap">
          <TextInput placeholder="ex : Loyer perçu" value={nouvSource} onChange={e => setNouvSource(e.currentTarget.value)} style={{ flex: 1 }} />
          <ActionIcon size="lg" onClick={ajouterSource} aria-label="Ajouter la source"><IconPlus size={18} /></ActionIcon>
        </Group>
      </Carte>

      <Carte titre="🔐 Changer le mot de passe">
        <Stack gap="sm" maw={420}>
          <PasswordInput label="Mot de passe actuel" autoComplete="current-password"
                         value={mdpActuel} onChange={e => setMdpActuel(e.currentTarget.value)} />
          <PasswordInput label="Nouveau mot de passe (6 caractères min.)" autoComplete="new-password"
                         value={mdpNouveau} onChange={e => setMdpNouveau(e.currentTarget.value)} />
          <Button onClick={changerMdp} loading={envoiMdp} style={{ alignSelf: 'flex-start' }}>Mettre à jour</Button>
        </Stack>
      </Carte>
    </Stack>
  );
}
