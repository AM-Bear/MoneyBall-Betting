import path from 'path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, type Plugin } from 'vite';

import runtimeErrorOverlay from '@replit/vite-plugin-runtime-error-modal';
import seoConfig from './seo-config.json';

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

type SeoMetadata = {
  title: string;
  description: string;
  canonicalPath: string;
  indexable: boolean;
  public: boolean;
};

const seoRoutes = seoConfig.routes as Record<string, SeoMetadata>;
const seoAliases = seoConfig.aliases as Record<string, string>;

function routeMetadataFor(pathname: string) {
  return seoRoutes[seoAliases[pathname] ?? pathname] ?? seoRoutes['/404'];
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function updateSeoTag(html: string, tagName: 'meta' | 'link', marker: string, value: string) {
  const tagPattern = new RegExp(
    `<${tagName}\\b(?=[^>]*data-seo=["']${marker}["'])[^>]*>`,
    'i',
  );
  const match = html.match(tagPattern);
  if (!match) return html;

  const attributePattern = tagName === 'link'
    ? /\bhref=["'][^"']*["']/i
    : /\bcontent=["'][^"']*["']/i;
  const attribute = tagName === 'link' ? 'href' : 'content';
  return html.replace(tagPattern, match[0].replace(
    attributePattern,
    `${attribute}="${escapeHtml(value)}"`,
  ));
}

function routeMetadataPlugin(): Plugin {
  return {
    name: 'moneyline-route-metadata',
    transformIndexHtml: {
      order: 'pre',
      handler(html, context) {
        const pathname = new URL(context.originalUrl || context.path, 'http://localhost').pathname;
        const normalizedPath = pathname === '/'
          ? '/'
          : `/${pathname.replace(/^\/+|\/+$/g, '')}`;
        const metadata = routeMetadataFor(normalizedPath);
        const siteUrl = seoConfig.siteUrl.replace(/\/+$/, '');
        const canonicalUrl = `${siteUrl}${metadata.canonicalPath === '/' ? '' : metadata.canonicalPath}`;
        const imageUrl = `${siteUrl}${seoConfig.socialImagePath}`;

        let updated = html.replace(
          /<title\b[^>]*data-seo=["']title["'][^>]*>.*?<\/title>/i,
          `<title data-seo="title" data-seo-title>${escapeHtml(metadata.title)}</title>`,
        );
        for (const [tagName, marker, value] of [
          ['meta', 'description', metadata.description],
          ['meta', 'robots', metadata.indexable ? 'index, follow' : 'noindex, follow'],
          ['meta', 'og-title', metadata.title],
          ['meta', 'og-description', metadata.description],
          ['meta', 'og-url', canonicalUrl],
          ['meta', 'og-image', imageUrl],
          ['meta', 'og-image-width', '1200'],
          ['meta', 'og-image-height', '630'],
          ['meta', 'og-image-alt', 'MONEYLINE transparent baseball research desk'],
          ['meta', 'twitter-title', metadata.title],
          ['meta', 'twitter-description', metadata.description],
          ['meta', 'twitter-image', imageUrl],
          ['meta', 'twitter-image-alt', 'MONEYLINE transparent baseball research desk'],
          ['link', 'canonical', canonicalUrl],
        ] as const) {
          updated = updateSeoTag(updated, tagName, marker, value);
        }
        return updated;
      },
    },
  };
}

export default defineConfig(async ({ command, isPreview }) => ({
  base: basePath,
  plugins: [
    routeMetadataPlugin(),
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
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;

          // Charts are only needed by the record/backtest panels. Keep
          // Recharts and its D3 modules out of the initial desk entry.
          if (
            id.includes('/recharts/') ||
            id.includes('/d3-') ||
            id.includes('/internmap/')
          ) {
            return 'charts';
          }

          // Radix primitives are shared by panels, but are not required to
          // paint the first shell. Group them so they load independently.
          if (id.includes('/@radix-ui/')) return 'radix';

          if (
            id.includes('/lucide-react/') ||
            id.includes('/react-icons/') ||
            id.includes('/framer-motion/')
          ) {
            return 'ui-vendor';
          }

          return undefined;
        },
      },
    },
  },
}));
