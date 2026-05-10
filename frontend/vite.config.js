/* global process */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

const devCertPath = fileURLToPath(new URL('./certs/dev.pfx', import.meta.url))
const useHttps = process.env.VITE_HTTPS === 'true'

function getHttpsOptions() {
  if (!useHttps) return undefined

  if (!fs.existsSync(devCertPath)) {
    throw new Error('Missing HTTPS certificate. Run npm.cmd run dev:https to create it.')
  }

  return {
    pfx: fs.readFileSync(devCertPath),
    passphrase: process.env.VITE_HTTPS_CERT_PASSWORD || 'blind-ocr-dev',
  }
}

export default defineConfig({
  plugins: [
    react(),
    basicSsl()
  ],
  server: {
    allowedHosts: ['blind-ocr-web-phucle.loca.lt', 'localhost', '127.0.0.1'],
    strictPort: true,
    host: true,
    strictPort: true,
    host: true,
    https: true,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
