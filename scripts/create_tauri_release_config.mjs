#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const outputArgument = process.argv[2];
const publicKey = process.env.TAURI_UPDATER_PUBLIC_KEY?.trim();
const repository = process.env.GITHUB_REPOSITORY?.trim();

if (!outputArgument) {
  throw new Error("Usage: create_tauri_release_config.mjs <output-path>");
}
if (!publicKey) {
  throw new Error("TAURI_UPDATER_PUBLIC_KEY is required");
}
if (!repository || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
  throw new Error("GITHUB_REPOSITORY must have the form owner/repository");
}

const outputPath = resolve(outputArgument);
const config = {
  bundle: {
    createUpdaterArtifacts: true,
  },
  plugins: {
    updater: {
      pubkey: publicKey,
      endpoints: [
        `https://github.com/${repository}/releases/latest/download/latest.json`,
      ],
    },
  },
};

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(config, null, 2)}\n`, {
  encoding: "utf8",
  mode: 0o600,
});
console.log(`Created ephemeral updater configuration at ${outputPath}`);
