import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MantineProvider, localStorageColorSchemeManager } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import dayjs from 'dayjs';
import 'dayjs/locale/fr';

import '@mantine/core/styles.css';
import '@mantine/dates/styles.css';
import '@mantine/notifications/styles.css';
import './global.css';

import { theme } from './theme';
import App from './App';
import { MiseAJour } from './components/MiseAJour';

dayjs.locale('fr');

const queryClient = new QueryClient({
  defaultOptions: {
    // Pas de nouvel essai automatique (chaque échec afficherait une notification de plus),
    // rechargement à chaque affichage d'un écran comme l'ancien frontend.
    queries: { retry: false, refetchOnWindowFocus: false, staleTime: 0 },
    mutations: { retry: false },
  },
});

// Même clé que l'ancien frontend (« theme » = 'light' | 'dark') : le choix est conservé
const colorSchemeManager = localStorageColorSchemeManager({ key: 'theme' });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark" colorSchemeManager={colorSchemeManager}>
      <DatesProvider settings={{ locale: 'fr', firstDayOfWeek: 1 }}>
        <QueryClientProvider client={queryClient}>
          <ModalsProvider>
            {/* En bas à droite (au-dessus de la barre d’onglets sur mobile) : ne masque jamais la navigation */}
            <Notifications position="bottom-right" limit={3} containerWidth={380} />
            <MiseAJour />
            <App />
          </ModalsProvider>
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>
  </StrictMode>,
);
