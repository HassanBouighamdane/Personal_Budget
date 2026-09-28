import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// En développement, Vite (port 5173) redirige /api vers FastAPI (port 8500) :
// même origine pour le navigateur, donc cookie de session et CORS inchangés.
// En production, `npm run build` produit dist/, servi directement par FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8500' },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200,
  },
});
