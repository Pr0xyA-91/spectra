import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '..')

const CANONICAL_ROOT_ASSETS = [
  { outName: 'favicon.ico', srcFile: 'icon.ico', contentType: 'image/x-icon' },
  { outName: 'icon.png', srcFile: 'icon.png', contentType: 'image/png' },
  { outName: 'logo.svg', srcFile: 'spectra_logo.svg', contentType: 'image/svg+xml' },
]

function canonicalRootIconsPlugin() {
  return {
    name: 'spectra-canonical-root-icons',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const cleanUrl = (req.url || '').split('?')[0]
        const match = CANONICAL_ROOT_ASSETS.find((a) => `/${a.outName}` === cleanUrl)
        if (!match) return next()
        const fullPath = path.join(REPO_ROOT, match.srcFile)
        if (!fs.existsSync(fullPath)) return next()
        res.setHeader('Content-Type', match.contentType)
        fs.createReadStream(fullPath).pipe(res)
      })
    },
    generateBundle() {
      for (const asset of CANONICAL_ROOT_ASSETS) {
        const fullPath = path.join(REPO_ROOT, asset.srcFile)
        if (fs.existsSync(fullPath)) {
          this.emitFile({
            type: 'asset',
            fileName: asset.outName,
            source: fs.readFileSync(fullPath),
          })
        }
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), canonicalRootIconsPlugin()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/lucide-react')) {
            return 'vendor-icons';
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
})
