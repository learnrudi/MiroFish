import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), {
    name: 'native-setup-loopback',
    configResolved(config) {
      if (config.env.VITE_NATIVE_SETUP === '1' && config.command === 'serve' &&
          (![ '127.0.0.1', 'localhost' ].includes(config.server.host) ||
           ![ '127.0.0.1', 'localhost' ].includes(config.preview.host))) {
        throw new Error('Native setup requires explicit loopback frontend and preview binds.')
      }
    },
  }],
  preview: { host: '127.0.0.1' },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@locales': path.resolve(__dirname, '../locales')
    }
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: process.env.MIROFISH_BACKEND_URL || 'http://localhost:5001',
        changeOrigin: true,
        secure: false
      }
    }
  }
})
