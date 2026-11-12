import { useState } from 'react';
import { Button, Group, ScrollArea, Stack, Text, TextInput, Tooltip, ActionIcon } from '@mantine/core';
import { IconCalendarOff, IconDeviceFloppy, IconPlus } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr, MOIS_FR } from '../../lib/format';
import type { Titre } from '../../lib/types';
import { useEcriture, useJoursFeries, useTitres } from '../../lib/queries';
import { IconBuildingSkyscraper, IconReceiptTax } from '@tabler/icons-react';
import { ChampDate } from '../../components/champs';
import { IndicesSuivis } from './Comparaison';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Vide } from '../../components/ui';

/** Jours où la Bourse est fermée : aucun cours de clôture n'est noté (les week-ends non plus) */
function JoursFeries() {
  const { data, isPending } = useJoursFeries();
  const ecrire = useEcriture('bourse');
  const [jour, setJour] = useState(auj());
  const [libelle, setLibelle] = useState('');
  const aVenir = (data?.variables ?? []).filter(f => f.date >= auj().slice(0, 4) + '-01-01');

  function ajouter() {
    ecrire.mutate({ path: '/api/bourse/jours-feries', method: 'POST', body: { date: jour, libelle: libelle.trim() }, succes: 'Jour férié ajouté ✓' },
                  { onSuccess: () => setLibelle('') });
  }

  return (
    <Carte titre="Jours fériés de la Bourse" icone={<Pastille icone={IconCalendarOff} couleur="ambre" />}
           description="Ces jours-là, comme les week-ends, aucun cours de clôture n'est noté">
      <Stack gap="sm">
        <Info>
          Déjà connus chaque année : {data?.fixes.map(f => `${f.jour} ${MOIS_FR[f.mois - 1].toLowerCase()} (${f.libelle})`).join(', ') ?? '…'}.
          Les fêtes religieuses (Aïd al-Fitr, Aïd al-Adha, 1er Moharram, Aïd al-Mawlid) changent de date chaque année :
          ajoute-les dès que leur date est annoncée.
        </Info>
        {isPending ? <Chargement lignes={2} /> : aVenir.length > 0 && (
          <Stack gap={2}>
            {aVenir.map(f => (
              <Group key={f.date} className="ligne-op" justify="space-between" wrap="nowrap" gap="sm" px={6} py={4}>
                <Text fz="sm">{dateFr(f.date)}{f.libelle ? <Text span inherit c="dimmed"> · {f.libelle}</Text> : null}</Text>
                <BoutonSuppr onClick={() => ecrire.mutate({ path: `/api/bourse/jours-feries/${f.date}`, method: 'DELETE', succes: 'Jour férié retiré' })} />
              </Group>
            ))}
          </Stack>
        )}
        <Group gap="xs" align="flex-end" wrap="wrap">
          <ChampDate label="Jour" value={jour} onChange={setJour} />
          <TextInput label="Fête (optionnel)" placeholder="ex : Aïd al-Fitr" value={libelle} onChange={e => setLibelle(e.currentTarget.value)}
                     maxLength={100} style={{ flex: 1, minWidth: 160 }} />
          <Button onClick={ajouter} loading={ecrire.isPending} leftSection={<IconPlus size={15} />}>Ajouter</Button>
        </Group>
      </Stack>
    </Carte>
  );
}

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

      <IndicesSuivis />

      <JoursFeries />

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
