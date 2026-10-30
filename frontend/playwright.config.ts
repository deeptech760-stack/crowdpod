import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:3000", headless: true },
  reporter: "list",
});
