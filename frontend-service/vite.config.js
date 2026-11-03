import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import path from 'path';
import { readFileSync } from 'fs';

// The version shown in the menu: given by make deploy (git), else the package version of a local build
const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'));

export default defineConfig({
  plugins: [sveltekit()],

  define: {
    __B2S_VERSION__: JSON.stringify(process.env.B2S_VERSION || `${pkg.version}-dev`),
    __B2S_BUILT_AT__: JSON.stringify(new Date().toISOString())
  },

  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        const isAdapterNodeUnusedImport =
          warning?.code === 'UNUSED_EXTERNAL_IMPORT' &&
          String(warning?.message ?? '').includes('try_get_request_store') &&
          String(warning?.message ?? '').includes('.svelte-kit/adapter-node/index.js');

        if (isAdapterNodeUnusedImport) return;
        warn(warning);
      }
    }
  },

  server: {
    port: 3000,
    strictPort: true
  },

  resolve: {
    alias: {
      // Alias global vers routes/(app)
      $appRoutes: path.resolve('src/routes/(app)'),

      // Alias spécifique storage-roots (optionnel mais très utile)
      $storageRoots: path.resolve('src/routes/(app)/storage-roots')
    }
  }
});
