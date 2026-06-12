import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  plugins: [sveltekit()],

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
