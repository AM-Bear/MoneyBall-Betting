import path from 'path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

import runtimeErrorOverlay from '@replit/vite-plugin-runtime-error-modal';

// PORT is only needed when vite actually serves (dev / preview). Production
// builds run in the deploy pipeline without a PORT, so only enforce it there.
const rawPort = process.env.PORT;
const port = rawPort ? Number(rawPort) : undefined;

if (rawPort && (Number.isNaN(port) || (port as number) <= 0)) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

function requirePort(command: string): number {
  if (port == null) {
    throw new Error(
      `PORT environment variable is required for "vite ${command}" but was not provided.`,
    );
  }
  return port;
}

// The app is served at the root path in production; BASE_PATH can override.
const basePath = process.env.BASE_PATH || '/';

export default defineConfig(async ({ command, isPreview }) => ({
  base: basePath,
  plugins: [
    react(),
    tailwindcss(),
    runtimeErrorOverlay(),
    ...(process.env.NODE_ENV !== 'production' &&
    process.env.REPL_ID !== undefined
      ? [
          await import('@replit/vite-plugin-cartographer').then((m) =>
            m.cartographer({
              root: path.resolve(import.meta.dirname, '..'),
            }),
          ),
          await import('@replit/vite-plugin-dev-banner').then((m) =>
            m.devBanner(),
          ),
        ]
      : []),
  ],
  server:
    command === 'serve' && !isPreview
      ? {
          port: requirePort('dev'),
          strictPort: true,
          host: '0.0.0.0' as const,
          allowedHosts: true as const,
          fs: {
            strict: true,
          },
        }
      : undefined,
  preview: isPreview
    ? {
        port: requirePort('preview'),
        host: '0.0.0.0' as const,
        allowedHosts: true as const,
      }
    : undefined,
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, 'src'),
      '@assets': path.resolve(
        import.meta.dirname,
        '..',
        '..',
        'attached_assets',
      ),
    },
    dedupe: ['react', 'react-dom'],
  },
  root: path.resolve(import.meta.dirname),
  build: {
    outDir: path.resolve(import.meta.dirname, 'dist/public'),
    emptyOutDir: true,
  },
}));
