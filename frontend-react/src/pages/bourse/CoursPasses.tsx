/* Bourse → Paramètres — cours passés des titres : les clôtures notées chaque soir ne commencent qu'à la mise en place de
 * l'historique ; un fichier « Market Data → Cours » de la Bourse de Casablanca (jusqu'à 3 ans) couvre les jours d'avant.
 * Ils servent à la courbe du portefeuille, à la reconstitution du patrimoine et à la comparaison avec l'indice. */
import { Badge, Button, Group, Table, Text } from '@mantine/core';
import { IconHistory } from '@tabler/icons-react';

import { dateFr } from '../../lib/format';
import type { CouvertureTitre } from '../../lib/types';
import { useCouvertureCours, useEcriture } from '../../lib/queries';
import { ouvrirImportSerie } from '../../components/ImportSerie';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Tableau, Vide } from '../../components/ui';

const couvre = (t: CouvertureTitre) => !!t.debut && t.debut <= t.premier_achat;

export function ouvrirImportCours(titre: string, titres: CouvertureTitre[]) {
  ouvrirImportSerie({
    titreFenetre: 'Importer des cours passés', titre: 'Titre', module: 'bourse', initial: titre,
    series: titres.map(t => ({ value: t.titre, label: t.titre + (t.detenu ? '' : ' (vendu)') })),
    chemin: c => `/api/bourse/historique/${encodeURIComponent(c)}/import`,
    debutConseille: c => titres.find(t => t.titre === c)?.premier_achat ?? null,
    aide: <>Sur le site de la Bourse de Casablanca, <b>Market Data → Cours</b> : choisis le titre et une période (jusqu'à 3 ans),
      puis « Télécharger les données (Excel) ». Le fichier se dépose tel quel ; la colonne du cours de clôture est choisie
      d'elle-même. Une clôture déjà notée le soir est gardée.</>,
  });
}

export function CoursPassesTitres() {
  const { data, isPending } = useCouvertureCours();
  const ecrire = useEcriture('bourse');
  const titres = data ?? [];
  return (
    <Carte titre="Cours passés des titres" icone={<Pastille icone={IconHistory} couleur="emeraude" />}
           description="Les clôtures sont notées chaque soir depuis la mise en place de l'historique ; importe les jours d'avant">
      {isPending ? <Chargement lignes={3} /> : !titres.length ? <Vide>Aucun titre acheté pour l'instant</Vide> : (
        <>
          <Tableau minWidth={520}>
            <Table.Thead>
              <Table.Tr><Table.Th>Titre</Table.Th><Table.Th>Cours connus</Table.Th><Table.Th /></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {titres.map(t => (
                <Table.Tr key={t.titre}>
                  <Table.Td>
                    <Text fz="sm" fw={600}>{t.titre}</Text>
                    {!t.detenu && <Badge size="xs" variant="light" color="gray" tt="none">vendu</Badge>}
                  </Table.Td>
                  <Table.Td>
                    <Text fz="sm">{t.nb ? `${t.nb} · du ${dateFr(t.debut!)} au ${dateFr(t.fin!)}` : 'aucun'}</Text>
                    {t.nb_import > 0 && <Text fz="xs" c="dimmed">dont {t.nb_import} importés</Text>}
                    {!couvre(t) && <Text fz="xs" c="ambre">ne couvre pas le premier achat ({dateFr(t.premier_achat)})</Text>}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={0} wrap="nowrap" justify="flex-end">
                      <Button size="compact-xs" variant={couvre(t) ? 'subtle' : 'light'} onClick={() => ouvrirImportCours(t.titre, titres)}>Importer</Button>
                      {t.nb_import > 0 && (
                        <BoutonSuppr label="Retirer les cours importés" onClick={() => confirmer(
                          `Retirer les ${t.nb_import} cours importés de ${t.titre} ? Les clôtures notées chaque soir restent.`,
                          () => ecrire.mutate({ path: `/api/bourse/historique/${encodeURIComponent(t.titre)}/import`, method: 'DELETE',
                                                succes: 'Cours importés retirés' }), 'Retirer')} />
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Tableau>
          <Info>
            Avec les cours passés, la courbe du portefeuille remonte jusqu'à ton premier achat, les fins de mois reconstituées du
            patrimoine utilisent la vraie clôture (au lieu du prix de ta dernière transaction), et la comparaison avec l'indice
            devient juste depuis le début.
          </Info>
        </>
      )}
    </Carte>
  );
}
