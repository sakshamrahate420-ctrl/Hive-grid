import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
const backend = process.env.HIVEGRID_API_TARGET ?? 'http://127.0.0.1:8000';
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      ['/health', '/simulation', '/homes', '/metrics', '/timeseries', '/events', '/society', '/grid']
        .map((path) => [path, { target: backend, changeOrigin: true }]),
    ),
  },
});
