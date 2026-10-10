import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// En développement, Vite (port 5173) redirige /api vers FastAPI (port 8500) :
// même origine pour le navigateur, donc cookie de session et CORS inchangés.
// En production, `npm run build` produit dist/, servi directement par FastAPI.
export default defineConfig({
  plugins: [
    react(),
    // Service worker : l'application (JS, CSS, icônes) est mise en cache sur l'appareil,
    // elle s'ouvre donc instantanément et même hors connexion. Les données (/api) ne sont
    // jamais mises en cache : elles viennent toujours du serveur.
    VitePWA({
      registerType: 'prompt', // nouvelle version → l'utilisateur choisit quand recharger (pas de saisie perdue)
      manifest: false,        // public/manifest.json reste la source du manifeste
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.origin === 'https://fonts.googleapis.com',
            handler: 'StaleWhileRevalidate',
            options: { cacheName: 'google-fonts-css' },
          },
          {
            urlPattern: ({ url }) => url.origin === 'https://fonts.gstatic.com',
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts',
              expiration: { maxEntries: 20, maxAgeSeconds: 365 * 24 * 3600 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: { '/api': 'http://localhost:8500' },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200,
  },
});
