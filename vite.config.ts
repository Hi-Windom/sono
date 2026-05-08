import { defineConfig, Plugin, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";
import fs from 'fs';
import path from 'path';

const LOG_FILE = path.join(process.cwd(), 'logs', 'app.log');

function ensureLogDir() {
  const logDir = path.dirname(LOG_FILE);
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }
}

function requestLogPlugin(): Plugin {
  return {
    name: 'request-log',
    configureServer(server) {
      ensureLogDir();

      server.middlewares.use('/api/log', (req, res) => {
        if (req.method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk.toString(); });
          req.on('end', () => {
            try {
              const data = JSON.parse(body);
              const timestamp = new Date().toISOString();
              const logEntry = `[${timestamp}] [Client] ${data.message}\n`;
              fs.appendFileSync(LOG_FILE, logEntry);
              res.writeHead(200, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ success: true }));
            } catch (e) {
              res.writeHead(400, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ error: 'Invalid JSON' }));
            }
          });
        } else if (req.method === 'GET') {
          res.writeHead(200, { 'Content-Type': 'text/plain' });
          if (fs.existsSync(LOG_FILE)) {
            res.end(fs.readFileSync(LOG_FILE, 'utf-8'));
          } else {
            res.end('');
          }
        } else {
          res.writeHead(405);
          res.end();
        }
      });

      server.middlewares.use((req, res, next) => {
        const start = Date.now();
        const originalEnd = res.end;
        res.end = function (...args: any[]) {
          const elapsed = Date.now() - start;
          const logEntry = `[${new Date().toISOString()}] [Vite] ${req.method} ${req.url} → ${res.statusCode} (${elapsed}ms) host=${req.headers.host}\n`;
          fs.appendFileSync(LOG_FILE, logEntry);
          return originalEnd.apply(res, args);
        };
        next();
      });
    },
    configurePreviewServer(server) {
      ensureLogDir();

      server.middlewares.use('/api/log', (req, res) => {
        if (req.method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk.toString(); });
          req.on('end', () => {
            try {
              const data = JSON.parse(body);
              const timestamp = new Date().toISOString();
              const logEntry = `[${timestamp}] [Client] ${data.message}\n`;
              fs.appendFileSync(LOG_FILE, logEntry);
              res.writeHead(200, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ success: true }));
            } catch (e) {
              res.writeHead(400, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ error: 'Invalid JSON' }));
            }
          });
        } else if (req.method === 'GET') {
          res.writeHead(200, { 'Content-Type': 'text/plain' });
          if (fs.existsSync(LOG_FILE)) {
            res.end(fs.readFileSync(LOG_FILE, 'utf-8'));
          } else {
            res.end('');
          }
        } else {
          res.writeHead(405);
          res.end();
        }
      });

      server.middlewares.use((req, res, next) => {
        const start = Date.now();
        const originalEnd = res.end;
        res.end = function (...args: any[]) {
          const elapsed = Date.now() - start;
          const logEntry = `[${new Date().toISOString()}] [Vite-Preview] ${req.method} ${req.url} → ${res.statusCode} (${elapsed}ms)\n`;
          fs.appendFileSync(LOG_FILE, logEntry);
          return originalEnd.apply(res, args);
        };
        next();
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd(), '');
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000';

  return {
    define: {
      '__BUILD_TIME__': JSON.stringify(new Date().toISOString()),
    },
    build: {
      sourcemap: 'hidden',
      rollupOptions: {
        output: {
          entryFileNames: `assets/[name].[hash].js`,
          chunkFileNames: `assets/[name].[hash].js`,
          assetFileNames: `assets/[name].[hash].[ext]`,
        },
      },
    },
    server: {
      allowedHosts: true,
      proxy: {
        '/api': {
          target: apiUrl,
          changeOrigin: true,
          bypass: (req) => {
            if (req.url?.startsWith('/api/log')) {
              return false;
            }
          },
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq, req) => {
              console.log(`[Proxy] → ${req.method} ${req.url} => ${apiUrl}${req.url}`);
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
          target: apiUrl,
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq, req) => {
              console.log(`[Proxy] → ${req.method} ${req.url} => ${apiUrl}${req.url}`);
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
      tsconfigPaths()
    ],
  };
});
