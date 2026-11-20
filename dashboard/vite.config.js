import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// `npm run build` writes dist/, which the FastAPI backend serves.
// `npm run dev` serves the front end on port 5173 and forwards /api to the backend on 8050.
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8050' } },
});
