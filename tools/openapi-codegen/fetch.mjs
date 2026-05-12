#!/usr/bin/env node
/**
 * fetch.mjs — Fetch /openapi.json from running services and write to staticSpec path.
 *
 * In CI, services are started in a docker-compose stack before this runs.
 * Locally: run individual services first, then `make openapi-fetch`.
 *
 * If a service is unreachable, falls back to the existing staticSpec file (offline mode).
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");
const registry = JSON.parse(
  fs.readFileSync(path.join(__dirname, "services.json"), "utf-8")
);

let anyFailed = false;

for (const svc of registry.services) {
  const outPath = path.join(root, svc.staticSpec);
  process.stdout.write(`Fetching ${svc.name} from ${svc.localUrl} ... `);

  try {
    // Use built-in fetch (Node 18+)
    const resp = await fetch(svc.localUrl, { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const spec = await resp.json();

    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(spec, null, 2) + "\n");
    console.log("✓");
  } catch (err) {
    console.log(`✗ (${err.message}) — using existing staticSpec`);
    if (!fs.existsSync(outPath)) {
      console.error(`  ERROR: No existing spec at ${outPath} and service unreachable.`);
      anyFailed = true;
    }
  }
}

if (anyFailed) process.exit(1);
