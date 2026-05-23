import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss()
  ],
  server: {
    allowedHosts: [
      'localhost',
      '127.0.0.1',
      'resort-everglade-untrained.ngrok-free.dev',
      'refer-promptly-msgid-common.trycloudflare.com',
      'same-acrylic-kirk-unity.trycloudflare.com'
    ],
  }
})