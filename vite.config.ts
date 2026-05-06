import { defineConfig, Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";
import { traeBadgePlugin } from 'vite-plugin-trae-solo-badge';

function requestLogPlugin(): Plugin {
  return {
    name: 'request-log',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const start = Date.now();
        const originalEnd = res.end;
        res.end = function (...args: any[]) {
          const elapsed = Date.now() - start;
          console.log(`[Vite] ${req.method} ${req.url} → ${res.statusCode} (${elapsed}ms) host=${req.headers.host}`);
          return originalEnd.apply(res, args);
        };
        next();
      });
    },
  };
}

export default defineConfig({
  build: {
    sourcemap: 'hidden',
  },
  server: {
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            console.log(`[Proxy] → ${req.method} ${req.url} => http://localhost:8000${req.url}`);
          });
          proxy.on('proxyRes', (proxyRes, req) => {
            console.log(`[Proxy] ← ${req.method} ${req.url} status=${proxyRes.statusCode}`);
          });
          proxy.on('error', (err, req) => {
            console.error(`[Proxy] ERROR ${req.method} ${req.url}: ${err.message}`);
          });
        },
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            console.log(`[Proxy] → ${req.method} ${req.url} => http://localhost:8000${req.url}`);
          });
          proxy.on('proxyRes', (proxyRes, req) => {
            console.log(`[Proxy] ← ${req.method} ${req.url} status=${proxyRes.statusCode}`);
          });
          proxy.on('error', (err, req) => {
            console.error(`[Proxy] ERROR ${req.method} ${req.url}: ${err.message}`);
          });
        },
      },
    },
  },
  plugins: [
    requestLogPlugin(),
    react({
      babel: {
        plugins: [
          'react-dev-locator',
        ],
      },
    }),
    traeBadgePlugin({
      variant: 'dark',
      position: 'bottom-right',
      prodOnly: true,
      clickable: true,
      clickUrl: 'https://www.trae.ai/solo?showJoin=1',
      autoTheme: true,
      autoThemeTarget: '#root'
    }),
    tsconfigPaths()
  ],
})
