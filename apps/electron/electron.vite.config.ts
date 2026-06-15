import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "tailwindcss";
import autoprefixer from "autoprefixer";

// No externalizeDepsPlugin: @skillctl/core (and its pure-JS deps yaml/zod) are
// bundled into the main process output so the app is self-contained and we avoid
// shipping a pnpm workspace symlink inside asar. `electron` and node builtins stay
// external automatically for the node-targeted main/preload builds.
export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        external: ["electron"],
      },
    },
  },
  preload: {},
  renderer: {
    plugins: [react()],
    css: {
      postcss: {
        plugins: [tailwindcss(), autoprefixer()],
      },
    },
  },
});
