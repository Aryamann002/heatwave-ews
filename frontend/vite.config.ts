import { defineConfig } from "vite";

// maplibre-gl >= 5 loads its web worker via import.meta.url next to its own module file.
// Vite's dependency pre-bundling moves the main file into node_modules/.vite/deps/ but
// leaves the worker behind (HTTP 404), so GeoJSON layers never render. Serve it from the package.
export default defineConfig({
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: { host: "0.0.0.0", port: 5173 },
});
