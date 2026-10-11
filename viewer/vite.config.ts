/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Relative base so `dist/` can be served from any path (or opened offline).
  base: './',
  build: {
    rollupOptions: {
      // Two pages: the PRD viewer (index.html) and the tactical heatmap view.
      input: {
        main: 'index.html',
        heatmap: 'heatmap.html',
      },
    },
  },
  test: {
    environment: 'node',
  },
});
