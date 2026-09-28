import { useEffect, useState } from 'react';
import { Button, Group, ScrollArea, Stack, TextInput, Tooltip, ActionIcon } from '@mantine/core';
import { IconDeviceFloppy, IconPlus } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { lireMontant, tauxEnPct } from '../../lib/format';
import type { Titre } from '../../lib/types';
import { useEcriture, useParametresBourse, useTitres } from '../../lib/queries';
import { IconBuildingSkyscraper, IconReceiptTax } from '@tabler/icons-react';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Vide } from '../../components/ui';

function LigneTitre({ t }: { t: Titre }) {
  const ecrire = useEcriture('bourse');
  const [code, setCode] = useState(t.code);
  const [nom, setNom] = useState(t.nom);
  const [secteur, setSecteur] = useState(t.secteur);
  const modifie = code !== t.code || nom !== t.nom || secteur !== t.secteur;

  function sauver() {
    if (!code.trim() || !nom.trim()) return toast('Code et nom requis', false);
    ecrire.mutate({ path: '/api/bourse/titres/' + t.id, method: 'PUT', succes: 'Titre mis à jour ✓',
      body: { code: code.trim(), nom: nom.trim(), secteur: secteur.trim() } });
  }

  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput value={code} onChange={e => setCode(e.currentTarget.value)} style={{ flex: 1 }} aria-label="Code" />
      <TextInput value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 2 }} aria-label="Nom" />
      <TextInput value={secteur} onChange={e => setSecteur(e.currentTarget.value)} style={{ flex: 1 }} aria-label="Secteur" />
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
  const { data: params } = useParametresBourse();
  const ecrire = useEcriture('bourse');
  const [code, setCode] = useState('');
  const [nom, setNom] = useState('');
  const [secteur, setSecteur] = useState('');
  const [tpcvm, setTpcvm] = useState('');

  useEffect(() => { if (params) setTpcvm(tauxEnPct(params.taux_tpcvm)); }, [params]);

  function ajouterTitre() {
    if (!code.trim() || !nom.trim()) return toast('Code et nom requis', false);
    ecrire.mutate(
      { path: '/api/bourse/titres', method: 'POST', succes: 'Titre ajouté ✓', body: { code: code.trim(), nom: nom.trim(), secteur: secteur.trim() } },
      { onSuccess: () => { setCode(''); setNom(''); setSecteur(''); } },
    );
  }

  function sauverParametres() {
    const taux = lireMontant(tpcvm);
    if (isNaN(taux) || taux < 0) return toast('Taux invalide', false);
    ecrire.mutate({ path: '/api/bourse/parametres', method: 'PUT', body: { taux_tpcvm: taux / 100 }, succes: 'Paramètres enregistrés ✓' });
  }

  return (
    <>
      <Carte titre="Titres BVC" description="Autocomplétion du champ « Titre » et regroupement par secteur" icone={<Pastille icone={IconBuildingSkyscraper} couleur="ocean" />}>
        {isPending ? <Chargement /> : !titres?.length ? <Vide>Aucun titre configuré</Vide> : (
          <ScrollArea.Autosize mah={340} type="auto" offsetScrollbars>
            <Stack gap="xs">
              {/* key incluant les valeurs : la ligne se réinitialise après un rechargement */}
              {titres.map(t => <LigneTitre key={`${t.id}|${t.code}|${t.nom}|${t.secteur}`} t={t} />)}
            </Stack>
          </ScrollArea.Autosize>
        )}
        <Stack gap="xs" mt="lg">
          <Info><b>Ajouter un titre</b></Info>
          <Group gap="xs" wrap="nowrap">
            <TextInput placeholder="Code (ex : ATW)" value={code} onChange={e => setCode(e.currentTarget.value)} style={{ flex: 1 }} />
            <TextInput placeholder="Nom de la société" value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 2 }} />
            <TextInput placeholder="Secteur" value={secteur} onChange={e => setSecteur(e.currentTarget.value)} style={{ flex: 1 }} />
            <ActionIcon size="lg" onClick={ajouterTitre} aria-label="Ajouter le titre"><IconPlus size={18} /></ActionIcon>
          </Group>
          <Info>
            Alimente l'autocomplétion du champ « Titre » et le regroupement par secteur des positions. Renommer un code met à
            jour les transactions, dividendes et cours déjà saisis sous l'ancien code.
          </Info>
        </Stack>
      </Carte>

      <Carte titre="Fiscalité" icone={<Pastille icone={IconReceiptTax} couleur="violet" />}>
        <Stack gap="xs">
          <TextInput label="Taux TPCVM — plus-values de cession (%)" inputMode="decimal" maw={320}
                     value={tpcvm} onChange={e => setTpcvm(e.currentTarget.value)} rightSection="%" />
          <Info>
            Appliqué automatiquement sur le gain réalisé à chaque vente (PRU en coût moyen pondéré). Calculé vente par vente :
            les pertes d'une vente ne compensent pas les gains d'une autre vente sur la même année — à vérifier auprès d'un
            professionnel si tu as plusieurs ventes dans l'année.
          </Info>
        </Stack>
      </Carte>

      <Carte>
        <Stack gap="sm">
          <Button onClick={sauverParametres} loading={ecrire.isPending} style={{ alignSelf: 'flex-start' }}>Enregistrer les paramètres</Button>
          <Info>
            Les prix de transaction, montants de dividendes et frais de compte (y compris les droits de garde, à saisir
            manuellement dans l'onglet Frais) sont désormais saisis directement (aucun frais de courtage n'est calculé
            automatiquement). Valeur indicative par défaut : TPCVM 15 %.
          </Info>
        </Stack>
      </Carte>
    </>
  );
}
