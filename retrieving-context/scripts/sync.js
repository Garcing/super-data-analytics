#!/usr/bin/env node
/**
 * sync.js — Node.js wrapper around the Python sync pipeline.
 *
 * Resolves the correct Python interpreter (via shared env.js, which reads
 * PYTHON_PATH from config.json), then spawns sync.py with all args passed through.
 *
 * Usage:
 *   node scripts/sync.js                 # full sync (feishu → graph → embed)
 *   node scripts/sync.js --only embed    # only rebuild embeddings
 *   node scripts/sync.js --dry-run       # preview feishu data
 *   node scripts/sync.js --download-model
 *   node scripts/sync.js --force-embed
 */
import { spawn } from "node:child_process";
import { join } from "node:path";

import { SCRIPTS_DIR, pythonPath } from "./env.js";

const scriptPath = join(SCRIPTS_DIR, "pipeline", "sync.py");
const child = spawn(pythonPath(), [scriptPath, ...process.argv.slice(2)], {
  stdio: "inherit",
  shell: true,
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
