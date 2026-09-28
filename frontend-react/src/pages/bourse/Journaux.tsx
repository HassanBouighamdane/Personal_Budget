/* Bourse — saisie et journaux : transactions, dividendes, frais de compte, apports/retraits.
 * Aucun frais n'est calculé automatiquement : l'utilisateur saisit le prix net et le montant net reçu. */
import { useMemo, useState } from 'react';
import { Autocomplete, Button, Group, NumberInput, Select, Stack, Table, Text, TextInput, type ComboboxItem } from '@mantine/core';

import { toast } from '../../lib/api';
import { auj, fmt, jjmm, jjmmaa, lireMontant } from '../../lib/format';
import { T } from '../../lib/palette';
import { useDividendes, useEcriture, useFraisBourse, useMouvements, useTitres, useTransactionsBourse } from '../../lib/queries';
import { ChampDate, ChampMontant } from '../../components/champs';
import { IconArrowsExchange, IconBuildingBank, IconCoins, IconReceiptTax } from '@tabler/icons-react';
import { Aide, BoutonSuppr, Carte, Chargement, confirmer, Grille2, Pastille, Tableau, ThTri, useTri, Vide } from '../../components/ui';

/* ---------- Champ « Titre » : autocomplétion par code OU par nom de société ---------- */
function ChampTitre({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: titres } = useTitres();
  const noms = useMemo(() => new Map((titres ?? []).map(t => [t.code, t.nom])), [titres]);
  return (
    <Autocomplete
      label="Titre"
      placeholder="ex : ATW ou tape le nom de la société"
      data={[...new Set((titres ?? []).map(t => t.code))]}
      value={value}
      onChange={onChange}
      limit={30}
      maxDropdownHeight={280}
      filter={({ options, search }) => {
        const s = search.trim().toLowerCase();
        if (!s) return options;
        return (options as ComboboxItem[]).filter(o =>
          o.value.toLowerCase().includes(s) || (noms.get(o.value) ?? '').toLowerCase().includes(s));
      }}
      renderOption={({ option }) => (
        <Group gap="xs" wrap="nowrap">
          <Text fz="sm" fw={700} className="chiffre">{option.value}</Text>
          <Text fz="sm" c="dimmed" truncate>{noms.get(option.value)}</Text>
        </Group>
      )}
    />
  );
}

const Montant = ({ v, positif, signe }: { v: number; positif: boolean; signe?: boolean }) => (
  <Table.Td className="num chiffre" c={positif ? T.rev : T.dep} fw={600}>{signe ? (positif ? '+ ' : '− ') : ''}{fmt(v)}</Table.Td>
);
const TdDate = ({ d, annee }: { d: string; annee?: boolean }) =>
  <Table.Td c="dimmed" style={{ whiteSpace: 'nowrap' }}>{annee ? jjmmaa(d) : jjmm(d)}</Table.Td>;

/* ================= Transactions ================= */
export function JournalTransactions() {
  const ecrire = useEcriture('bourse');
  const [date, setDate] = useState(auj());
  const [instrument, setInstrument] = useState('Action');
  const [titre, setTitre] = useState('');
  const [type, setType] = useState('Achat');
  const [qte, setQte] = useState<string | number>('');
  const [prix, setPrix] = useState('');
  const [frais, setFrais] = useState('');

  function ajouter() {
    const t = titre.trim().toUpperCase();
    const q = typeof qte === 'number' ? qte : parseFloat(qte);
    const p = lireMontant(prix);
    const f = frais ? lireMontant(frais) : 0;
    if (!t) return toast('Indique le titre', false);
    if (!q || q <= 0) return toast('Quantité invalide', false);
    if (isNaN(p) || p <= 0) return toast('Prix invalide', false);
    ecrire.mutate({
      path: '/api/bourse/transactions', method: 'POST', succes: 'Transaction ajoutée ✓',
      body: {
        date_operation: date, titre: t, type_instrument: instrument, type_operation: type,
        quantite: q, cours_unitaire: p, autres_frais: isNaN(f) ? 0 : f,
      },
    }, { onSuccess: () => { setTitre(''); setQte(''); setPrix(''); setFrais(''); } });
  }

  return (
    <>
      <Grille2>
        <Carte titre="Achat / Vente" description="Enregistre une opération de ton relevé de courtage" icone={<Pastille icone={IconArrowsExchange} couleur="safran" />}>
          <Stack gap="sm">
            <ChampDate value={date} onChange={setDate} />
            <Select label="Type d'instrument" value={instrument} onChange={v => v && setInstrument(v)} allowDeselect={false}
                    data={[{ value: 'Action', label: 'Action' }, { value: 'Obligation', label: 'Obligation' },
                           { value: 'OPCVM', label: 'OPCVM' }, { value: 'IPO', label: 'IPO / Souscription' }]} />
            <ChampTitre value={titre} onChange={setTitre} />
            <Select label="Type" value={type} onChange={v => v && setType(v)} allowDeselect={false} data={['Achat', 'Vente']} />
            <NumberInput label="Quantité" min={0} step={1} allowNegative={false} value={qte} onChange={setQte} />
            <ChampMontant label={instrument === 'OPCVM' ? 'Valeur liquidative nette (DH)' : 'Prix unitaire net (DH)'}
                          value={prix} onChange={setPrix} />
            <ChampMontant label="Frais de transaction (DH) — optionnel, si non compris dans le prix" value={frais} onChange={setFrais} />
            <Button mt="xs" onClick={ajouter} loading={ecrire.isPending}>Ajouter la transaction</Button>
          </Stack>
        </Carte>
        <Aide titre="Saisie manuelle">
            Aucun frais n'est calculé automatiquement : indique directement le prix
            net auquel l'opération a réellement eu lieu (celui de ton relevé de
            courtage). Le champ « Frais de transaction » est optionnel, pour une
            commission ponctuelle non comprise dans ce prix.<br /><br />
            Pour les frais récurrents (abonnement courtier, tenue de compte...),
            utilise plutôt l'onglet <b>Frais</b>.<br /><br />
            Le PRU (prix de revient unitaire) reste calculé automatiquement en
            coût moyen pondéré, tous instruments confondus par titre.
          </Aide>
      </Grille2>
      <TableTransactions />
    </>
  );
}

function TableTransactions() {
  const { data, isPending } = useTransactionsBourse();
  const ecrire = useEcriture('bourse');
  type Cle = 'date' | 'titre' | 'type' | 'qte' | 'net';
  const { triees, tri, basculer } = useTri<NonNullable<typeof data>[number], Cle>(data, (t, c) =>
    c === 'date' ? t.date_operation : c === 'titre' ? t.titre : c === 'type' ? t.type_operation : c === 'qte' ? t.quantite : t.montant_net,
    { cle: 'date', desc: true });
  const th = { tri, basculer };

  return (
    <Carte titre="Journal des transactions" description="Clique sur un en-tête de colonne pour trier">
      {isPending ? <Chargement /> : !data?.length ? (
        <Vide>Aucune transaction — ajoute ton premier achat ci-dessus 👆</Vide>
      ) : (
        <Tableau minWidth={720}>
          <Table.Thead>
            <Table.Tr>
              <ThTri cle="date" {...th}>Date</ThTri><ThTri cle="titre" {...th}>Titre</ThTri><Table.Th>Instrument</Table.Th>
              <ThTri cle="type" {...th}>Type</ThTri><ThTri cle="qte" num {...th}>Qté</ThTri>
              <Table.Th className="num">Prix</Table.Th><Table.Th className="num">Frais</Table.Th>
              <ThTri cle="net" num {...th}>Net</ThTri><Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {triees.map(t => {
              const achat = t.type_operation === 'Achat';
              return (
                <Table.Tr key={t.id}>
                  <TdDate d={t.date_operation} />
                  <Table.Td fw={600}>{t.titre}</Table.Td>
                  <Table.Td c="dimmed" fz="xs">{t.type_instrument}</Table.Td>
                  <Table.Td c={achat ? T.rev : T.dep}>{t.type_operation}</Table.Td>
                  <Table.Td className="num chiffre">{t.quantite}</Table.Td>
                  <Table.Td className="num chiffre">{fmt(t.cours_unitaire)}</Table.Td>
                  <Table.Td className="num chiffre">{fmt(t.autres_frais)}</Table.Td>
                  <Montant v={t.montant_net} positif={!achat} signe />
                  <Table.Td style={{ width: 40 }}>
                    <BoutonSuppr onClick={() => confirmer('Supprimer cette transaction ?', () =>
                      ecrire.mutate({ path: `/api/bourse/transactions/${t.id}`, method: 'DELETE', succes: 'Supprimé' }))} />
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Tableau>
      )}
    </Carte>
  );
}

/* ================= Dividendes ================= */
export function JournalDividendes() {
  const { data, isPending } = useDividendes();
  const ecrire = useEcriture('bourse');
  const [date, setDate] = useState(auj());
  const [titre, setTitre] = useState('');
  const [montant, setMontant] = useState('');

  function ajouter() {
    const t = titre.trim().toUpperCase();
    const m = lireMontant(montant);
    if (!t) return toast('Indique le titre', false);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate(
      { path: '/api/bourse/dividendes', method: 'POST', succes: 'Dividende ajouté ✓', body: { date_operation: date, titre: t, montant: m } },
      { onSuccess: () => { setTitre(''); setMontant(''); } },
    );
  }

  return (
    <>
      <Grille2>
        <Carte titre="Dividende reçu" description="Montant net crédité sur ton compte" icone={<Pastille icone={IconCoins} couleur="ocean" />}>
          <Stack gap="sm">
            <ChampDate value={date} onChange={setDate} />
            <ChampTitre value={titre} onChange={setTitre} />
            <ChampMontant label="Montant net reçu (DH)" value={montant} onChange={setMontant} />
            <Button mt="xs" color="ocean" onClick={ajouter} loading={ecrire.isPending}>Ajouter le dividende</Button>
          </Stack>
        </Carte>
        <Aide titre="Saisie manuelle">
            Indique directement le montant NET déjà reçu (après retenue à la
            source), tel qu'il apparaît sur ton relevé — aucun calcul de
            fiscalité n'est appliqué ici.
          </Aide>
      </Grille2>
      <Carte titre="Journal des dividendes">
        {isPending ? <Chargement /> : !data?.length ? <Vide>Aucun dividende — ajoute le premier ci-dessus 👆</Vide> : (
          <Tableau>
            <Table.Thead>
              <Table.Tr><Table.Th>Date</Table.Th><Table.Th>Titre</Table.Th><Table.Th className="num">Montant net</Table.Th><Table.Th /></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.map(d => (
                <Table.Tr key={d.id}>
                  <TdDate d={d.date_operation} />
                  <Table.Td fw={600}>{d.titre}</Table.Td>
                  <Table.Td className="num chiffre" c={T.rev} fw={600}>{fmt(d.montant)}</Table.Td>
                  <Table.Td style={{ width: 40 }}>
                    <BoutonSuppr onClick={() => confirmer('Supprimer ce dividende ?', () =>
                      ecrire.mutate({ path: `/api/bourse/dividendes/${d.id}`, method: 'DELETE', succes: 'Supprimé' }))} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Tableau>
        )}
      </Carte>
    </>
  );
}

/* ================= Frais de compte ================= */
export function JournalFrais() {
  const { data, isPending } = useFraisBourse();
  const ecrire = useEcriture('bourse');
  const [date, setDate] = useState(auj());
  const [libelle, setLibelle] = useState('');
  const [montant, setMontant] = useState('');

  function ajouter() {
    const m = lireMontant(montant);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate(
      { path: '/api/bourse/frais', method: 'POST', succes: 'Frais ajouté ✓', body: { date_operation: date, libelle: libelle.trim(), montant: m } },
      { onSuccess: () => { setLibelle(''); setMontant(''); } },
    );
  }

  return (
    <>
      <Grille2>
        <Carte titre="Frais de compte" description="Abonnement, tenue de compte, droits de garde…" icone={<Pastille icone={IconReceiptTax} couleur="safran" />}>
          <Stack gap="sm">
            <ChampDate value={date} onChange={setDate} />
            <TextInput label="Libellé" placeholder="ex : Abonnement Wafabourse" value={libelle} onChange={e => setLibelle(e.currentTarget.value)} />
            <ChampMontant label="Montant (DH)" value={montant} onChange={setMontant} />
            <Button mt="xs" onClick={ajouter} loading={ecrire.isPending}>Ajouter le frais</Button>
          </Stack>
        </Carte>
        <Aide titre="À quoi ça sert">
            Pour les frais indépendants d'une transaction précise : abonnement
            mensuel de ta plateforme (ex : 19 DH/mois Wafabourse), frais de
            tenue de compte, etc. Ils sont intégrés au résultat de la période
            dans le Dashboard.
          </Aide>
      </Grille2>
      <Carte titre="Journal des frais">
        {isPending ? <Chargement /> : !data?.length ? <Vide>Aucun frais enregistré — ajoute le premier ci-dessus 👆</Vide> : (
          <Tableau>
            <Table.Thead>
              <Table.Tr><Table.Th>Date</Table.Th><Table.Th>Libellé</Table.Th><Table.Th className="num">Montant</Table.Th><Table.Th /></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.map(f => (
                <Table.Tr key={f.id}>
                  <TdDate d={f.date_operation} />
                  <Table.Td>{f.libelle}</Table.Td>
                  <Table.Td className="num chiffre" c={T.dep} fw={600}>{fmt(f.montant)}</Table.Td>
                  <Table.Td style={{ width: 40 }}>
                    <BoutonSuppr onClick={() => confirmer('Supprimer ce frais ?', () =>
                      ecrire.mutate({ path: `/api/bourse/frais/${f.id}`, method: 'DELETE', succes: 'Supprimé' }))} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Tableau>
        )}
      </Carte>
    </>
  );
}

/* ================= Apports / retraits (banque <-> compte Bourse) ================= */
export function JournalMouvements() {
  const { data, isPending } = useMouvements();
  const ecrire = useEcriture('bourse');
  const [date, setDate] = useState(auj());
  const [type, setType] = useState('Apport');
  const [montant, setMontant] = useState('');
  const [libelle, setLibelle] = useState('');

  function ajouter() {
    const m = lireMontant(montant);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate({
      path: '/api/bourse/mouvements', method: 'POST', succes: 'Mouvement ajouté ✓',
      body: { date_operation: date, type_mouvement: type, montant: m, libelle: libelle.trim() },
    }, { onSuccess: () => { setMontant(''); setLibelle(''); } });
  }

  const apports = (data ?? []).filter(m => m.type_mouvement === 'Apport').reduce((s, m) => s + m.montant, 0);
  const retraits = (data ?? []).filter(m => m.type_mouvement === 'Retrait').reduce((s, m) => s + m.montant, 0);

  return (
    <>
      <Grille2>
        <Carte titre="Apport / Retrait" description="Virement entre ta banque et le compte Bourse" icone={<Pastille icone={IconBuildingBank} couleur="ocean" />}>
          <Stack gap="sm">
            <ChampDate value={date} onChange={setDate} />
            <Select label="Type" value={type} onChange={v => v && setType(v)} allowDeselect={false}
                    data={[{ value: 'Apport', label: 'Apport — banque → compte Bourse' },
                           { value: 'Retrait', label: 'Retrait — compte Bourse → banque' }]} />
            <ChampMontant label="Montant (DH)" value={montant} onChange={setMontant} />
            <TextInput label="Libellé (optionnel)" placeholder="ex : Virement vers Wafabourse"
                       value={libelle} onChange={e => setLibelle(e.currentTarget.value)} />
            <Button mt="xs" color="ocean" onClick={ajouter} loading={ecrire.isPending}>Ajouter le mouvement</Button>
          </Stack>
        </Carte>
        <Aide titre="Comment ça marche">
            Un virement de ta banque vers le compte Bourse est un <b>apport</b> :
            ce n'est pas une dépense, l'argent reste à toi. Ne le saisis donc
            <b> pas</b> dans l'onglet Saisie.<br /><br />
            Les gains de vente et les dividendes que tu laisses sur le compte
            n'ont rien à saisir ici : ils s'ajoutent automatiquement aux espèces
            disponibles, et un réinvestissement est simplement un nouvel achat.<br /><br />
            Saisis un <b>retrait</b> seulement quand de l'argent revient vers ta banque.
          </Aide>
      </Grille2>
      <Carte titre="Journal des apports et retraits">
        {isPending ? <Chargement /> : !data?.length ? <Vide>Aucun mouvement — ajoute ton premier apport ci-dessus 👆</Vide> : (
          <>
            <Text c="dimmed" fz="sm" mb="xs">
              Apports : <b>{fmt(apports)}</b> · Retraits : <b>{fmt(retraits)}</b> · Net investi : <b>{fmt(apports - retraits)}</b>
            </Text>
            <Tableau minWidth={480}>
              <Table.Thead>
                <Table.Tr><Table.Th>Date</Table.Th><Table.Th>Type</Table.Th><Table.Th>Libellé</Table.Th><Table.Th className="num">Montant</Table.Th><Table.Th /></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.map(m => {
                  const apport = m.type_mouvement === 'Apport';
                  return (
                    <Table.Tr key={m.id}>
                      <TdDate d={m.date_operation} annee />
                      <Table.Td>{m.type_mouvement}</Table.Td>
                      <Table.Td>{m.libelle}</Table.Td>
                      <Montant v={m.montant} positif={apport} signe />
                      <Table.Td style={{ width: 40 }}>
                        <BoutonSuppr onClick={() => confirmer('Supprimer ce mouvement ?', () =>
                          ecrire.mutate({ path: `/api/bourse/mouvements/${m.id}`, method: 'DELETE', succes: 'Supprimé' }))} />
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Tableau>
          </>
        )}
      </Carte>
    </>
  );
}
