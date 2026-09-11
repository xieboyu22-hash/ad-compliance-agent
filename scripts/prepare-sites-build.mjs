#!/usr/bin/env node
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const client = path.join(dist, "client");
const server = path.join(dist, "server");
const hostingOut = path.join(dist, ".openai");

const requiredFiles = [
  path.join(root, "index.html"),
  path.join(root, "worker", "index.js"),
  path.join(root, ".openai", "hosting.json"),
];

for (const file of requiredFiles) {
  if (!existsSync(file)) {
    throw new Error("Missing Sites build input: " + file);
  }
}

mkdirSync(client, { recursive: true });
mkdirSync(server, { recursive: true });
mkdirSync(hostingOut, { recursive: true });

copyFileSync(path.join(root, "index.html"), path.join(client, "index.html"));
copyFileSync(path.join(root, "worker", "index.js"), path.join(server, "index.js"));
copyFileSync(path.join(root, ".openai", "hosting.json"), path.join(hostingOut, "hosting.json"));

console.log("Prepared Sites build in dist/");
