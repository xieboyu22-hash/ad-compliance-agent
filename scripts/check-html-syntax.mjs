#!/usr/bin/env node
import { readFileSync } from "node:fs";

for (const file of ["ad-compliance-agent.html", "site/index.html", "index.html"]) {
  const html = readFileSync(file, "utf8");
  const script = html.match(/<script>([\s\S]*)<\/script>/)?.[1];
  if (!script) {
    throw new Error(`Missing inline script in ${file}`);
  }
  new Function(script);
  console.log(`${file} script syntax ok`);
}
