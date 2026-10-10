/* Bourse — récapitulatif fiscal d'une année : cessions, TPCVM retenue, dividendes */
import { ActionIcon, Box, Button, Group, Table, Text, Title, Tooltip } from '@mantine/core';
import {
  IconChevronLeft, IconChevronRight, IconCoins, IconReceiptTax, IconReportMoney, IconScale, IconTrendingDown, IconTrendingUp,
} from '@tabler/icons-react';

import { fmt } from '../../lib/format';
import { signe, T } from '../../lib/palette';
import { useFiscalite } from '../../lib/queries';
import { Aide, Carte, Chargement, GrilleKpi, Kpi, Tableau, Vide } from '../../components/ui';
import type { NavBourse } from './Bourse';

export function Fiscalite({ nav }: { nav: NavBourse }) {
  const { data: f } = useFiscalite(nav.annee);
  const courante = new Date().getFullYear();

  return (
    <>
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Box>
          <Title order={2} fz={18}>Fiscalité {nav.annee}</Title>
          <Text c="dimmed" fz="xs" mt={2}>Les montants à reporter sur ta déclaration, d'après tes saisies</Text>
        </Box>
        <Group gap={4} wrap="nowrap">
          <Tooltip label="Année précédente">
            <ActionIcon variant="default" size={36} radius="md" aria-label="Année précédente" onClick={() => nav.setAnnee(a => a - 1)}>
              <IconChevronLeft size={18} />
            </ActionIcon>
          </Tooltip>
          <Button variant="default" h={36} px="sm" fw={600} disabled={nav.annee === courante} onClick={() => nav.setAnnee(courante)}>
            Cette année
          </Button>
          <Tooltip label="Année suivante">
            <ActionIcon variant="default" size={36} radius="md" aria-label="Année suivante" onClick={() => nav.setAnnee(a => a + 1)}>
              <IconChevronRight size={18} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>

      {!f ? <Chargement lignes={6} /> : (
        <>
          <GrilleKpi>
            <Kpi label="Plus-values brutes" icone={IconTrendingUp} teinte="emeraude" valeur={fmt(f.plus_values_brutes)} couleur={T.ep}
                 aide={`${f.nb_ventes} vente${f.nb_ventes > 1 ? 's' : ''} · cessions : ${fmt(f.montant_cessions)}`} />
            <Kpi label="Moins-values brutes" icone={IconTrendingDown} teinte="rouge" valeur={fmt(f.moins_values_brutes)}
                 couleur={f.moins_values_brutes < 0 ? T.neg : undefined} />
            <Kpi label="Résultat net de cession" icone={IconScale} teinte="marque" valeur={fmt(f.resultat_cessions)} couleur={signe(f.resultat_cessions)}
                 aide="plus-values − moins-values" />
            <Kpi label="TPCVM retenue" icone={IconReceiptTax} teinte="rose" valeur={fmt(f.tpcvm_retenue)} couleur={T.dep}
                 aide={`au taux de ${(f.taux_tpcvm * 100).toLocaleString('fr-FR')} % sur le résultat net : ${fmt(f.tpcvm_theorique)}`} />
            <Kpi label="Écart de TPCVM" icone={IconReportMoney} teinte="gray" valeur={fmt(f.ecart_tpcvm)}
                 aide={f.ecart_tpcvm > 0 ? 'retenue supérieure au taux appliqué au résultat net' : f.ecart_tpcvm < 0 ? 'retenue inférieure au taux appliqué au résultat net' : 'aucun écart'} />
            <Kpi label="Dividendes nets" icone={IconCoins} teinte="emeraude" valeur={fmt(f.dividendes_nets)} couleur={T.ep}
                 aide={`frais de compte de l'année : ${fmt(f.frais_compte)}`} />
          </GrilleKpi>

          <Carte titre="Détail par titre">
            {!f.par_titre.length ? <Vide>Aucune vente ni dividende en {nav.annee}</Vide> : (
              <Tableau minWidth={620}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Titre</Table.Th><Table.Th className="num">Ventes</Table.Th><Table.Th className="num">Cessions</Table.Th>
                    <Table.Th className="num">Gain brut</Table.Th><Table.Th className="num">TPCVM</Table.Th><Table.Th className="num">Dividendes nets</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {f.par_titre.map(t => (
                    <Table.Tr key={t.titre}>
                      <Table.Td fw={600}>{t.titre}</Table.Td>
                      <Table.Td className="num chiffre">{t.nb_ventes || '—'}</Table.Td>
                      <Table.Td className="num chiffre">{t.nb_ventes ? fmt(t.cessions) : '—'}</Table.Td>
                      <Table.Td className="num chiffre" c={signe(t.gain_brut)}>{t.nb_ventes ? fmt(t.gain_brut) : '—'}</Table.Td>
                      <Table.Td className="num chiffre">{t.nb_ventes ? fmt(t.tpcvm) : '—'}</Table.Td>
                      <Table.Td className="num chiffre" c={T.rev}>{t.dividendes ? fmt(t.dividendes) : '—'}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Tableau>
            )}
          </Carte>

          <Aide titre="À savoir">
            Ces chiffres viennent de tes saisies : la TPCVM est celle de tes avis d'opéré, les dividendes sont nets
            de la retenue à la source. Le montant « au taux sur le résultat net » applique le taux des paramètres au
            résultat de l'année (gains − pertes) : un repère pour vérifier tes retenues, pas un calcul fiscal officiel.
            Vérifie les règles d'imputation des moins-values avec ton intermédiaire ou la DGI.
          </Aide>
        </>
      )}
    </>
  );
}
