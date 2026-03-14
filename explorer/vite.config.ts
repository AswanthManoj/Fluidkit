import path from 'path'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite';
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), svelte()],
  base: '/',
  server: {
    port: 3000,
    proxy: {
      '/meta': 'http://localhost:8000',
      '/remote': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: '../fluidkit/explorer/static',
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      $lib: path.resolve('./src/lib'),
    },
  },
})
