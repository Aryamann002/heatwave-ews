import { defineConfig } from "vite";
import { resolve } from "node:path";

// maplibre-gl >= 5 loads its web worker via import.meta.url next to its own module file.
// Vite's dependency pre-bundling moves the main file into node_modules/.vite/deps/ but
// leaves the worker behind (HTTP 404), so GeoJSON layers never render. Serve it from the package.
export default defineConfig({
  optimizeDeps: { exclude: ["maplibre-gl"] },
  plugins: [{
    name: "heatsafe-landing-at-root",
    configureServer(server) {
      server.middlewares.use((request, _response, next) => {
        if (request.url === "/" || request.url?.startsWith("/?")) {
          request.url = `/landing.html${request.url.slice(1)}`;
        }
        next();
      });
    },
  }],
  build: { rolldownOptions: { input: {
    index: resolve(import.meta.dirname, "index.html"),
    landing: resolve(import.meta.dirname, "landing.html"),
    login: resolve(import.meta.dirname, "login.html"),
    dashboard: resolve(import.meta.dirname, "dashboard.html"),
  } } },
  server: { host: "0.0.0.0", port: 5173 },
});
