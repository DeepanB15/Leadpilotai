import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: { extend: { fontSize: { xs: ["12px", "16px"], sm: ["13px", "18px"] } } },
  plugins: [],
};
export default config;
