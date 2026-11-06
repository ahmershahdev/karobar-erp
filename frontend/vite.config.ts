/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

import { seoPlugin } from './build/seo-plugin';

// The production server swaps this placeholder for a fresh nonce on every response
// (deploy/nginx/site.conf), and Vite stamps it on every script and style tag it writes.
const CSP_NONCE_PLACEHOLDER = '__CSP_NONCE__';

export default defineConfig(({ command, mode }) => {
  // Local dev and preview work without a .env.local; production builds must set it explicitly.
  if (command === 'serve') process.env.VITE_SITE_URL ??= 'http://localhost:5173';
  const env = { ...loadEnv(mode, process.cwd(), 'VITE_'), ...process.env };
  return {
    plugins: [
      react(),
      tailwindcss(),
      ...(mode === 'test' ? [] : [seoPlugin(env.VITE_SITE_URL ?? '')]),
    ],
    html: mode === 'production' ? { cspNonce: CSP_NONCE_PLACEHOLDER } : {},
    server: {
      port: 5173,
      proxy: { '/api': { target: env.VITE_DEV_API_PROXY ?? 'http://127.0.0.1:8000' } },
    },
    build: {
      target: 'es2022',
      sourcemap: false,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
