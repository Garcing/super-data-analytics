/**
 * env.js — shared config helpers for the GraphRAG scripts.
 *
 * Both sync.js and query.js need to (1) read the project .env and
 * (2) resolve the Python interpreter. That logic lived duplicated in
 * each file; it is consolidated here.
 *
 * Path assumptions:
 *   - this file lives at <root>/scripts/env.js
 *   - PROJECT_ROOT  = <root>            (.env + graph-config.yaml live here)
 *   - SCRIPTS_DIR   = <root>/scripts    (all .js + .py entry points)
 */
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const SCRIPTS_DIR = dirname(fileURLToPath(import.meta.url));
export const PROJECT_ROOT = resolve(SCRIPTS_DIR, "..");

/**
 * Parse a simple KEY=VALUE .env file into a plain object (no dotenv dep).
 * Missing file → empty object (callers fall back to defaults).
 */
export function loadEnv(envPath = join(PROJECT_ROOT, ".env")) {
  const env = {};
  try {
    const content = readFileSync(envPath, "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq === -1) continue;
      env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
    }
  } catch {
    // .env missing — callers handle defaults
  }
  return env;
}

/**
 * Resolve the Python interpreter, preferring .env PYTHON_PATH and
 * falling back to the system `python`. Solves the case where the
 * agent's bundled Python lacks neo4j / sentence-transformers.
 */
export function pythonPath(env = loadEnv()) {
  return env.PYTHON_PATH || "python";
}
