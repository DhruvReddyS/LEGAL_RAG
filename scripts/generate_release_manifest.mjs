#!/usr/bin/env node
// Write the install page's release data from a directory of real build artifacts.
//
//   node scripts/generate_release_manifest.mjs <artifact-dir> <version> <base-url> [output]
//
// The checksums are computed here from the files, so the page can only ever show
// a checksum for a file that existed. Output defaults to frontend/public/releases.json.

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readdir, stat, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

const INSTALLER = /\.(dmg|msi|exe|appimage|deb|rpm)$|\.app\.tar\.gz$/i;

async function sha256(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

const [dir, version, baseUrl, output = "frontend/public/releases.json"] = process.argv.slice(2);
if (!dir || !version || !baseUrl) {
  console.error("usage: generate_release_manifest.mjs <artifact-dir> <version> <base-url> [output]");
  process.exit(2);
}
if (!baseUrl.startsWith("https://")) {
  console.error("base-url must be https");
  process.exit(2);
}

const artifacts = [];
for (const name of (await readdir(dir)).sort()) {
  if (!INSTALLER.test(name)) continue;
  const path = join(dir, name);
  const info = await stat(path);
  if (!info.isFile()) continue;
  artifacts.push({
    name,
    sha256: await sha256(path),
    bytes: info.size,
    url: `${baseUrl.replace(/\/+$/, "")}/${encodeURIComponent(name)}`,
  });
}
if (!artifacts.length) {
  console.error(`no installers found in ${dir}`);
  process.exit(1);
}

const target = resolve(output);
await mkdir(dirname(target), { recursive: true });
await writeFile(
  target,
  `${JSON.stringify({ version, published: new Date().toISOString().slice(0, 10), artifacts }, null, 2)}\n`,
);
console.log(`Wrote ${artifacts.length} artifact(s) to ${target}`);
