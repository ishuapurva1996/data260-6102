import { defineConfig } from "vite";

export default defineConfig({
  // Development only. Production assets are served by the existing FastAPI app.
  server: {
    strictPort: true,
    proxy: { "/api": { target: "https://localhost:8702", secure: false } },
  },
});
