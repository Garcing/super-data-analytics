/**
 * env.js — shared config helpers for the GraphRAG scripts.
 *
 * Single source of truth: ~/.super-data-analytics/config.json (same file
 * querying-data uses). Both sync.js and query.js read credentials + graph
 * config from here; no .env, no graph-config.yaml.
 *
 * Path assumptions:
 *   - this file lives at <root>/scripts/env.js
 *   - PROJECT_ROOT  = <root>            (retrieving-context/)
 *   - SCRIPTS_DIR   = <root>/scripts    (all .js + .py entry points)
 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const SCRIPTS_DIR = dirname(fileURLToPath(import.meta.url));
export const PROJECT_ROOT = resolve(SCRIPTS_DIR, "..");

export const CONFIG_PATH = join(homedir(), ".super-data-analytics", "config.json");

/**
 * Load & parse the shared config.json. Throws a clear, agent-facing error
 * when the file is missing or unreadable so the caller can guide the user
 * to fill it in.
 */
export function loadConfig(configPath = CONFIG_PATH) {
  let raw;
  try {
    raw = readFileSync(configPath, "utf-8");
  } catch (err) {
    if (err.code === "ENOENT") {
      throw new Error(
        `配置文件不存在: ${configPath}\n` +
          `请把 Neo4j / 飞书 / Python 凭证写入 config.json 的 env 块，graph-config 块放实体与关系后重试。`
      );
    }
    throw new Error(`读取配置失败 ${configPath}: ${err.message}`);
  }

  try {
    return JSON.parse(raw);
  } catch (err) {
    throw new Error(`解析配置失败 ${configPath}: ${err.message}`);
  }
}

/**
 * Resolve the Python interpreter, preferring config.json's env.PYTHON_PATH
 * and falling back to the system `python`. Solves the case where the
 * agent's bundled Python lacks neo4j / sentence-transformers.
 */
export function pythonPath(config = loadConfig()) {
  return config?.env?.PYTHON_PATH || "python";
}
