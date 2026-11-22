import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const api = "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    // The API, the map's basemap tiles and the index's CSV downloads all come from the Python service.
    proxy: { "/api": api, "/tiles": api, "/data": api },
  },
});
