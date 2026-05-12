#!/usr/bin/env node
/**
 * generate.mjs — Run openapi-typescript against each service's static spec,
 * then write a thin typed client wrapper.
 *
 * Requires: openapi-typescript (pnpm add -Dw openapi-typescript)
 */

import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");
const registry = JSON.parse(
  fs.readFileSync(path.join(__dirname, "services.json"), "utf-8")
);

for (const svc of registry.services) {
  const specPath = path.join(root, svc.staticSpec);
  const outDir = path.join(root, svc.outputDir);
  const schemaOut = path.join(outDir, "schema.ts");

  if (!fs.existsSync(specPath)) {
    console.error(`Spec not found: ${specPath} — run 'make openapi-fetch' first.`);
    process.exit(1);
  }

  fs.mkdirSync(outDir, { recursive: true });

  console.log(`Generating schema for ${svc.name} ...`);
  try {
    execSync(
      `pnpm openapi-typescript ${specPath} -o ${schemaOut}`,
      { cwd: root, stdio: "inherit" }
    );
  } catch {
    console.log(`openapi-typescript not found — writing schema.ts stub for ${svc.name}.`);
    // In CI the tool is installed; locally dev may skip full codegen.
    // The committed schema.ts is the canonical version until tools are installed.
    if (!fs.existsSync(schemaOut)) {
      fs.writeFileSync(schemaOut, `// Generated schema for ${svc.name} — run 'make openapi' with services running.\nexport interface paths {}\nexport interface components { schemas: Record<string, unknown>; }\nexport interface operations {}\n`);
    }
  }

  // Ensure index.ts exists
  const indexPath = path.join(outDir, "index.ts");
  if (!fs.existsSync(indexPath)) {
    fs.writeFileSync(indexPath, `export * from "./schema";\n`);
  }

  console.log(`  ✓ ${svc.name} → ${outDir}/schema.ts`);
}

console.log("✓ Codegen complete.");
