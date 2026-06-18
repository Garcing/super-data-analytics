#!/usr/bin/env node
/**
 * sync.js — Node.js wrapper for Python sync pipeline
 *
 * Resolves the correct Python interpreter from .env (PYTHON_PATH),
 * then spawns sync.py with all arguments passed through.
 *
 * Usage: node sync.js [any sync.py arguments]
 *   node sync.js                    # full sync
 *   node sync.js --only embed       # only rebuild embeddings
 *   node sync.js --dry-run          # preview
 *   node sync.js --download-model   # download embedding model
 *   node sync.js --force-embed      # force regenerate embeddings
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = resolve(__dirname, "..");

// Load .env
function loadPythonPath() {
  const envPath = join(PROJECT_ROOT, ".env");
  try {
    const content = readFileSync(envPath, "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eqIndex = trimmed.indexOf("=");
      if (eqIndex === -1) continue;
      const key = trimmed.slice(0, eqIndex).trim();
      if (key === "PYTHON_PATH") {
        return trimmed.slice(eqIndex + 1).trim();
      }
    }
  } catch {
    // .env not found
  }
  return "python";
}

const pythonPath = loadPythonPath();
const scriptPath = join(PROJECT_ROOT, "sync", "sync.py");
const args = process.argv.slice(2);

const child = spawn(pythonPath, [scriptPath, ...args], {
  stdio: "inherit",
  shell: true,
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
