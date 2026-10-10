/* Nouvelle version déployée : le service worker l'a téléchargée, on propose de recharger.
   Pas de rechargement automatique : une saisie en cours serait perdue. */
import { useEffect } from 'react';
import { Button, Group, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useRegisterSW } from 'virtual:pwa-register/react';

const ID = 'mise-a-jour';

export function MiseAJour() {
  const { needRefresh: [aRecharger], updateServiceWorker } = useRegisterSW({
    onRegisteredSW(_url, enregistrement) {
      // Application ouverte longtemps depuis l'écran d'accueil : vérifie les mises à jour toutes les heures
      if (enregistrement) setInterval(() => enregistrement.update(), 60 * 60 * 1000);
    },
  });

  useEffect(() => {
    if (!aRecharger) return;
    notifications.show({
      id: ID,
      color: 'marque',
      autoClose: false,
      withCloseButton: true,
      message: (
        <Group justify="space-between" wrap="nowrap" gap="sm">
          <Text size="sm">Nouvelle version disponible</Text>
          <Button size="xs" color="marque" onClick={() => updateServiceWorker(true)}>Recharger</Button>
        </Group>
      ),
    });
  }, [aRecharger, updateServiceWorker]);

  return null;
}
