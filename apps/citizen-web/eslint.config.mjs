// eslint-config-next 16 ships native flat configs, so they are imported
// directly rather than through the `FlatCompat` shim.
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    // Stated explicitly so the plugin does not probe the filesystem for it.
    settings: { react: { version: "19.3" } },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
];

export default config;
