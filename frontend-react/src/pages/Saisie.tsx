import { useState } from 'react';
import { Button, SegmentedControl, Select, Stack, Table, Text, TextInput } from '@mantine/core';
import { IconMinus, IconPlus } from '@tabler/icons-react';

import { toast } from '../lib/api';
import { auj, fmt, jjmm, lireMontant } from '../lib/format';
import { T } from '../lib/palette';
import { useConfig, useEcriture, useTransactionsMois } from '../lib/queries';
import { ChampDate, ChampMontant } from '../components/champs';
import { BoutonSuppr, Carte, Chargement, confirmer, Grille2, Tableau, Vide } from '../components/ui';

const AUTRE = '__autre__';

export function Saisie() {
  return (
    <Stack gap="md">
      <Grille2>
        <FormDepense />
        <FormRevenu />
      </Grille2>
      <TransactionsDuMois />
    </Stack>
  );
}

function FormDepense() {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const [date, setDate] = useState(auj());
  const [categorie, setCategorie] = useState<string | null>(null);
  const [montant, setMontant] = useState('');
  const [description, setDescription] = useState('');

  function ajouter() {
    const m = lireMontant(montant);
    if (!categorie) return toast('Choisis une catégorie', false);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate(
      { path: '/api/depenses', method: 'POST', body: { date, categorie, description, montant: m }, succes: 'Dépense ajoutée ✓' },
      { onSuccess: () => { setMontant(''); setDescription(''); } },
    );
  }

  // Sans doublon : Mantine refuse deux options de même valeur (les noms sont uniques en base)
  const cats = [...new Set(config?.categories.map(c => c.nom))];
  return (
    <Carte titre={<><IconMinus size={16} color="var(--c-dep)" style={{ verticalAlign: -2 }} /> Nouvelle dépense</>}>
      <Stack gap="sm">
        <ChampDate value={date} onChange={setDate} />
        <Select label="Catégorie" placeholder="— Choisir une catégorie —" data={cats} searchable
                nothingFoundMessage="Aucune catégorie"
                value={categorie && cats.includes(categorie) ? categorie : null} onChange={setCategorie} />
        <ChampMontant label="Montant (DH)" value={montant} onChange={setMontant} />
        <TextInput label="Description (optionnel)" placeholder="ex : courses Marjane"
                   value={description} onChange={e => setDescription(e.currentTarget.value)} />
        <Button mt="xs" onClick={ajouter} loading={ecrire.isPending}>Ajouter la dépense</Button>
      </Stack>
    </Carte>
  );
}

function FormRevenu() {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const [date, setDate] = useState(auj());
  const [source, setSource] = useState<string | null>(null);
  const [autre, setAutre] = useState('');
  const [montant, setMontant] = useState('');

  function ajouter() {
    const m = lireMontant(montant);
    let s = source;
    if (!s) return toast('Choisis une source', false);
    if (s === AUTRE) {
      s = autre.trim();
      if (!s) return toast('Précise la source', false);
    }
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate(
      { path: '/api/revenus', method: 'POST', body: { date, source: s, montant: m }, succes: 'Revenu ajouté ✓' },
      { onSuccess: () => { setMontant(''); setAutre(''); } },
    );
  }

  const noms = [...new Set(config?.sources.map(s => s.nom))];
  const valeur = source && (source === AUTRE || noms.includes(source)) ? source : null;
  return (
    <Carte titre={<><IconPlus size={16} color="var(--c-rev)" style={{ verticalAlign: -2 }} /> Nouveau revenu</>}>
      <Stack gap="sm">
        <ChampDate value={date} onChange={setDate} />
        <Select label="Source" placeholder="— Choisir une source —"
                data={[...noms.map(n => ({ value: n, label: n })), { value: AUTRE, label: 'Autre…' }]}
                value={valeur} onChange={setSource} />
        {valeur === AUTRE && (
          <TextInput placeholder="Précise la source..." value={autre} onChange={e => setAutre(e.currentTarget.value)} />
        )}
        <ChampMontant label="Montant (DH)" value={montant} onChange={setMontant} />
        <Button mt="xs" color="ocean" onClick={ajouter} loading={ecrire.isPending}>Ajouter le revenu</Button>
      </Stack>
    </Carte>
  );
}

type Ligne = { id: number; type: 'depenses' | 'revenus'; date: string; lbl: string; montant: number };

function TransactionsDuMois() {
  const { data, isPending } = useTransactionsMois(auj().slice(0, 7));
  const ecrire = useEcriture('budget');
  const [filtre, setFiltre] = useState<'tout' | 'depenses' | 'revenus'>('tout');

  const lignes: Ligne[] = data ? [
    ...data.depenses.map(x => ({ id: x.id, type: 'depenses' as const, date: x.date, montant: x.montant,
      lbl: x.categorie + (x.description ? ' — ' + x.description : '') })),
    ...data.revenus.map(x => ({ id: x.id, type: 'revenus' as const, date: x.date, montant: x.montant, lbl: x.source || 'Revenu' })),
  ].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id) : [];
  const visibles = filtre === 'tout' ? lignes : lignes.filter(l => l.type === filtre);

  const supprimer = (l: Ligne) => confirmer('Supprimer cette ligne ?', () =>
    ecrire.mutate({ path: `/api/${l.type}/${l.id}`, method: 'DELETE', succes: 'Supprimé' }));

  return (
    <Carte titre="🧾 Transactions du mois" droite={lignes.length > 0 && (
      <SegmentedControl size="xs" value={filtre} onChange={v => setFiltre(v as typeof filtre)}
        data={[{ value: 'tout', label: 'Tout' }, { value: 'depenses', label: 'Dépenses' }, { value: 'revenus', label: 'Revenus' }]} />
    )}>
      {isPending ? <Chargement /> : !lignes.length ? (
        <Vide>Aucune transaction ce mois — commence ta saisie ! 👆</Vide>
      ) : (
        <Tableau>
          <Table.Tbody>
            {visibles.map(l => {
              const dep = l.type === 'depenses';
              return (
                <Table.Tr key={l.type + l.id}>
                  <Table.Td c="dimmed" style={{ whiteSpace: 'nowrap', width: 60 }}>{jjmm(l.date)}</Table.Td>
                  <Table.Td>{l.lbl}</Table.Td>
                  <Table.Td className="num chiffre" fw={600}>
                    <Text span inherit c={dep ? T.dep : T.rev}>{dep ? '−' : '+'} {fmt(l.montant)}</Text>
                  </Table.Td>
                  <Table.Td style={{ width: 40 }}><BoutonSuppr onClick={() => supprimer(l)} /></Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Tableau>
      )}
    </Carte>
  );
}
