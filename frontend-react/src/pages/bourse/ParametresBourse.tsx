import { useState } from 'react';
import { Group, ScrollArea, Stack, TextInput, Tooltip, ActionIcon } from '@mantine/core';
import { IconDeviceFloppy, IconPlus } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import type { Titre } from '../../lib/types';
import { useEcriture, useTitres } from '../../lib/queries';
import { IconBuildingSkyscraper, IconReceiptTax } from '@tabler/icons-react';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Vide } from '../../components/ui';

function LigneTitre({ t }: { t: Titre }) {
  const ecrire = useEcriture('bourse');
  const [code, setCode] = useState(t.code);
  const [nom, setNom] = useState(t.nom);
  const [secteur, setSecteur] = useState(t.secteur);
  const [isin, setIsin] = useState(t.isin ?? '');
  const modifie = code !== t.code || nom !== t.nom || secteur !== t.secteur || isin !== (t.isin ?? '');

  function sauver() {
    if (!code.trim() || !nom.trim()) return toast('Code et nom requis', false);
    ecrire.mutate({ path: '/api/bourse/titres/' + t.id, method: 'PUT', succes: 'Titre mis à jour ✓',
      body: { code: code.trim(), nom: nom.trim(), secteur: secteur.trim(), isin: isin.trim() || null } });
  }

  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput value={code} onChange={e => setCode(e.currentTarget.value)} style={{ flex: 1 }} aria-label="Code" />
      <TextInput value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 2 }} aria-label="Nom" />
      <TextInput value={secteur} onChange={e => setSecteur(e.currentTarget.value)} style={{ flex: 1 }} aria-label="Secteur" />
      <TextInput value={isin} onChange={e => setIsin(e.currentTarget.value)} style={{ flex: 1 }} aria-label="ISIN" placeholder="ISIN" />
      <Tooltip label="Enregistrer" withArrow>
        <ActionIcon variant={modifie ? 'filled' : 'default'} size="lg" onClick={sauver} loading={ecrire.isPending} aria-label="Enregistrer">
          <IconDeviceFloppy size={16} />
        </ActionIcon>
      </Tooltip>
      <BoutonSuppr label="Retirer" onClick={() => confirmer('Retirer ce titre de la liste ? (les transactions déjà saisies sont conservées)',
        () => ecrire.mutate({ path: '/api/bourse/titres/' + t.id, method: 'DELETE', succes: 'Titre retiré' }), 'Retirer')} />
    </Group>
  );
}

export function ParametresBourse() {
  const { data: titres, isPending } = useTitres();
  const ecrire = useEcriture('bourse');
  const [code, setCode] = useState('');
  const [nom, setNom] = useState('');
  const [secteur, setSecteur] = useState('');
  const [isin, setIsin] = useState('');

  function ajouterTitre() {
    if (!code.trim() || !nom.trim()) return toast('Code et nom requis', false);
    ecrire.mutate(
      { path: '/api/bourse/titres', method: 'POST', succes: 'Titre ajouté ✓', body: { code: code.trim(), nom: nom.trim(), secteur: secteur.trim(), isin: isin.trim() || null } },
      { onSuccess: () => { setCode(''); setNom(''); setSecteur(''); setIsin(''); } },
    );
  }

  return (
    <>
      <Carte titre="Titres BVC" description="Autocomplétion du champ « Titre », regroupement par secteur et ISIN des cours automatiques" icone={<Pastille icone={IconBuildingSkyscraper} couleur="bleu" />}>
        {isPending ? <Chargement /> : !titres?.length ? <Vide>Aucun titre configuré</Vide> : (
          <ScrollArea.Autosize mah={340} type="auto" offsetScrollbars>
            <Stack gap="xs">
              {/* key incluant les valeurs : la ligne se réinitialise après un rechargement */}
              {titres.map(t => <LigneTitre key={`${t.id}|${t.code}|${t.nom}|${t.secteur}|${t.isin}`} t={t} />)}
            </Stack>
          </ScrollArea.Autosize>
        )}
        <Stack gap="xs" mt="lg">
          <Info><b>Ajouter un titre</b></Info>
          <Group gap="xs" wrap="nowrap">
            <TextInput placeholder="Code (ex : ATW)" value={code} onChange={e => setCode(e.currentTarget.value)} style={{ flex: 1 }} />
            <TextInput placeholder="Nom de la société" value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 2 }} />
            <TextInput placeholder="Secteur" value={secteur} onChange={e => setSecteur(e.currentTarget.value)} style={{ flex: 1 }} />
            <TextInput placeholder="ISIN" value={isin} onChange={e => setIsin(e.currentTarget.value)} style={{ flex: 1 }} />
            <ActionIcon size="lg" onClick={ajouterTitre} aria-label="Ajouter le titre"><IconPlus size={18} /></ActionIcon>
          </Group>
          <Info>
            Alimente l'autocomplétion du champ « Titre » et le regroupement par secteur des positions. Renommer un code met à
            jour les transactions, dividendes et cours déjà saisis sous l'ancien code. Les cours sont récupérés
            automatiquement par code ; l'ISIN ne sert qu'à la source de secours.
          </Info>
        </Stack>
      </Carte>

      <Carte titre="Fiscalité" icone={<Pastille icone={IconReceiptTax} couleur="marque" />}>
        <Info>
          Rien n'est calculé automatiquement : le prix, les frais de transaction et la TPCVM de chaque vente se saisissent
          dans l'onglet des transactions, tels qu'ils figurent sur l'avis d'opéré. Les dividendes (montant net) et les frais
          de compte, droits de garde compris, se saisissent dans leurs onglets respectifs.
        </Info>
      </Carte>
    </>
  );
}
