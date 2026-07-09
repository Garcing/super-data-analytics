#!/usr/bin/env node
/**
 * query.js — Node.js vector search + graph expansion CLI for GraphRAG
 *
 * Usage:
 *   node scripts/query.js --schema
 *   node scripts/query.js --question "<问题>" [--top-k 5] [--targets 表,指标]
 *   node scripts/query.js --cypher "<CYPHER>"
 *
 * --question / --cypher 各支持三态输入：
 *   --question "<文本>"   inline
 *   --question @<file>    文件
 *   --question -          stdin（管道）
 *
 * Flow (vector mode):
 *   1. Encode question via Python embedding subprocess
 *   2. Search Neo4j vector indexes for each target entity
 *   3. Expand graph context via relationships
 *   4. Output JSON to stdout (logs go to stderr)
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import neo4j from "neo4j-driver";

// ---------------------------------------------------------------------------
// Paths & config (merged from the former env.js; only this CLI uses them)
// ---------------------------------------------------------------------------
const SCRIPTS_DIR = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(SCRIPTS_DIR, "..");
const CONFIG_PATH = join(homedir(), ".super-data-analytics", "config.json");

/**
 * Load & parse the shared config.json. Throws a clear, agent-facing error
 * when the file is missing or unreadable so the caller can guide the user
 * to fill it in.
 */
function loadConfig(configPath = CONFIG_PATH) {
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

// ---------------------------------------------------------------------------
// Internal properties to exclude from output
// ---------------------------------------------------------------------------
const INTERNAL_PROPS = new Set([
  "search_text",
  "embedding",
  "embedding_model",
  "embedding_dimensions",
  "embedding_updated_at",
]);

// ---------------------------------------------------------------------------
// Config + model path helpers
// ---------------------------------------------------------------------------

/**
 * Local model directory is conventional, derived from the HF model id's
 * last segment: BAAI/bge-small-zh-v1.5 → scripts/pipeline/models/bge-small-zh-v1.5
 */
function modelDirFromConfig(gc) {
  const model = gc?.embedding?.model;
  if (!model) return null;
  const basename = String(model).split("/").pop();
  if (!basename) return null;
  return `scripts/pipeline/models/${basename}`;
}

// ---------------------------------------------------------------------------
// Tri-state text source resolution (--question / --cypher)
// ---------------------------------------------------------------------------

/**
 * Resolve a tri-state input value into its raw text.
 *   "@" + path  → read file
 *   "-" / null  → stdin (with a first-byte timeout so non-TTY callers
 *                 that forgot to close stdin don't hang forever)
 *   other       → inline string as-is
 */
async function resolveText(value, kind) {
  if (value === null || value === "-") {
    return readFromStdin(kind);
  }
  if (value.startsWith("@")) {
    const filePath = value.slice(1);
    if (!filePath) {
      console.error(`[query] ${kind} 值为 "@"，缺少文件路径`);
      process.exit(1);
    }
    try {
      return readFileSync(filePath, "utf-8").trim();
    } catch (err) {
      console.error(`[query] 无法读取 ${kind} 文件 ${filePath}: ${err.message}`);
      process.exit(1);
    }
  }
  if (!value) {
    console.error(`[query] ${kind} 内容为空`);
    process.exit(1);
  }
  return value;
}

async function readFromStdin(kind) {
  const stream = process.stdin;
  if (typeof stream.setEncoding === "function") stream.setEncoding("utf8");

  const timeoutMs = Number(process.env.QUERY_STDIN_TIMEOUT_MS) || 15000;

  const readPromise = (async () => {
    let content = "";
    for await (const chunk of stream) content += chunk;
    return content.trim();
  })();

  let timer;
  const timeoutPromise = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("STDIN_READ_TIMEOUT")), timeoutMs);
  });

  let content;
  try {
    content = await Promise.race([readPromise, timeoutPromise]);
  } catch (err) {
    if (stream.destroy) stream.destroy();
    if (err && err.message === "STDIN_READ_TIMEOUT") {
      console.error(
        `[query] 等待 stdin 超时（${timeoutMs / 1000}s 内未收到 ${kind}）。\n` +
          `常见原因：非交互环境里既没传 --${kind} "<文本>" / --${kind} @<文件>，stdin 也没关闭。\n` +
          `解决：用 --${kind} 显式传入，或确保管道写完后关闭 stdin。`
      );
      process.exit(1);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!content) {
    console.error(`[query] stdin 中的 ${kind} 为空`);
    process.exit(1);
  }
  return content;
}

// ---------------------------------------------------------------------------
// Encode question via Python subprocess
// ---------------------------------------------------------------------------

function encodeQuestion(text, modelPath, pyPath) {
  const scriptPath = join(SCRIPTS_DIR, "pipeline", "embedding.py");
  const absModelPath = resolve(PROJECT_ROOT, modelPath);

  console.error(`[query] Encoding question via Python...`);
  console.error(`[query]   python: ${pyPath}`);
  console.error(`[query]   script: ${scriptPath}`);
  console.error(`[query]   model:  ${absModelPath}`);

  let stdout;
  try {
    // 注意：不要加 shell:true。args 以原生 argv 数组传递，text 作为单个 token
    // 原样到达 Python（含空格/引号/特殊符号/换行都不被切词）。shell:true 会把
    // 数组拼成字符串交 shell 重新切词，含空格的问题（如 "GMV 是什么"）会被拆成
    // 多个 argv 导致 argparse 报 unrecognized arguments。
    const buffer = execFileSync(
      pyPath,
      [scriptPath, "encode", text, "--model-path", absModelPath],
      { encoding: "utf-8", timeout: 60000 }
    );
    stdout = buffer;
  } catch (err) {
    console.error("[query] Python encode failed:", err.message);
    if (err.stderr) console.error(err.stderr);
    process.exit(1);
  }

  try {
    return JSON.parse(stdout.trim());
  } catch {
    console.error("[query] Failed to parse Python output:", stdout);
    process.exit(1);
  }
}

// ---------------------------------------------------------------------------
// Vector index search
// ---------------------------------------------------------------------------

/**
 * Discover the actual vector index name for a given label from the database.
 * Returns the index name or null if not found.
 */
async function findVectorIndexName(session, label) {
  try {
    const result = await session.run(
      "SHOW VECTOR INDEXES YIELD name, labelsOrTypes"
    );
    for (const record of result.records) {
      const labels = record.get("labelsOrTypes");
      if (labels && labels.includes(label)) {
        return record.get("name");
      }
    }
  } catch {
    // ignore
  }
  return null;
}

async function searchVectorIndex(session, indexName, label, embedding, topK) {
  const escLabel = label.replace(/`/g, "``");

  const cypher = `
    CALL db.index.vector.queryNodes($indexName, $topK, $embedding)
    YIELD node, score
    WHERE node:\`${escLabel}\`
    RETURN elementId(node) AS id, score, properties(node) AS properties
    ORDER BY score DESC
  `;

  try {
    const result = await session.run(cypher, {
      indexName,
      topK: neo4j.int(topK),
      embedding,
    });

    return result.records.map((record) => ({
      id: record.get("id"),
      score: record.get("score"),
      properties: record.get("properties"),
    }));
  } catch (err) {
    console.error(
      `[query] Vector search failed for ${label} (${indexName}): ${err.message}`
    );
    return [];
  }
}

// ---------------------------------------------------------------------------
// Graph context expansion
// ---------------------------------------------------------------------------

async function fetchGraphContext(session, label, nodeId, relationships) {
  // 扩图阶段：边在 sync 阶段已按 match / via 配置建好写入库里，
  // 这里只沿已有边走，用节点 elementId 定位起点，不再读 match / source_field。
  // 这样 match 型（字段值匹配）和 via 型（中间表关联）的关系一视同仁，
  // 建图怎么建的不用关心 —— 边在库里就能走。
  const context = {};

  const relevantRels = relationships.filter(
    (rel) => rel.from === label || rel.to === label
  );

  for (const rel of relevantRels) {
    const isFrom = rel.from === label;
    const isTo = rel.to === label;
    const otherLabel = isFrom ? rel.to : rel.from;

    const escOther = otherLabel.replace(/`/g, "``");
    const escRelType = rel.type.replace(/`/g, "``");

    // 方向：自环（from===to，如 表-关联-表）走无向；否则按 from/to 判方向
    let relPattern;
    if (isFrom && isTo) {
      relPattern = `-[:\`${escRelType}\`]-`;
    } else if (isFrom) {
      relPattern = `-[:\`${escRelType}\`]->`;
    } else {
      relPattern = `<-[:\`${escRelType}\`]-`;
    }

    // 自环时排除起点自身，避免把同一个节点当邻居返回
    const selfExclude =
      otherLabel === label ? ` AND elementId(other) <> $nodeId` : "";

    const cypher = `
      MATCH (n)${relPattern}(other:\`${escOther}\`)
      WHERE elementId(n) = $nodeId${selfExclude}
      RETURN properties(other) AS props
      LIMIT 20
    `;

    try {
      const result = await session.run(cypher, { nodeId });

      if (result.records.length > 0) {
        if (!context[otherLabel]) context[otherLabel] = [];

        for (const record of result.records) {
          context[otherLabel].push(cleanProperties(record.get("props")));
        }
      }
    } catch (err) {
      console.error(
        `[query] Graph expansion failed for ${label}-${rel.type}-${otherLabel}: ${err.message}`
      );
    }
  }

  return context;
}

// ---------------------------------------------------------------------------
// Cypher query mode
// ---------------------------------------------------------------------------

async function runCypher(driver, database, cypher) {
  const session = driver.session({ database });
  try {
    const result = await session.run(cypher);
    const rows = result.records.map((record) => {
      const obj = {};
      for (const key of record.keys) {
        let val = record.get(key);

        if (neo4j.isInt(val)) {
          val = val.toNumber();
        }

        if (val && typeof val === "object" && val.properties) {
          val = cleanProperties(val.properties);
        }

        if (Array.isArray(val)) {
          val = val.map((v) => {
            if (neo4j.isInt(v)) return v.toNumber();
            if (v && typeof v === "object" && v.properties)
              return cleanProperties(v.properties);
            return v;
          });
        }

        obj[key] = val;
      }
      return obj;
    });
    return rows;
  } finally {
    await session.close();
  }
}

// ---------------------------------------------------------------------------
// Schema introspection (--schema): list entities + relationships
// ---------------------------------------------------------------------------

function buildSchema(gc) {
  const entities = [];
  for (const [label, cfg] of Object.entries(gc.entities || {})) {
    entities.push({
      label,
      key_field: cfg.key_field,
      table_id: cfg.table_id,
      vector_index: cfg.vector_index !== false,
    });
  }

  const relationships = (gc.relationships || []).map((rel) => {
    const out = { type: rel.type, from: rel.from, to: rel.to };
    if (rel.match) {
      out.match = {
        source_field: rel.match.source_field,
        target_field: rel.match.target_field,
      };
    }
    if (rel.via) {
      out.via = {
        table_id: rel.via.table_id,
        from_field: rel.via.from_field,
        to_field: rel.via.to_field,
        properties: rel.via.properties || [],
      };
    }
    return out;
  });

  return {
    embedding: gc.embedding || {},
    entities,
    relationships,
  };
}

// ---------------------------------------------------------------------------
// Clean properties helper
// ---------------------------------------------------------------------------

function cleanProperties(rawProps) {
  const clean = {};
  for (const [k, v] of Object.entries(rawProps)) {
    if (!INTERNAL_PROPS.has(k)) {
      clean[k] = v;
    }
  }
  return clean;
}

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = argv.slice(2);
  let question = null;
  let cypher = null;
  let topK = 5;
  let targets = null;
  let schema = false;
  let hasQuestion = false;
  let hasCypher = false;

  // 读取 --question / --cypher 的值：
  //   下一个 token 不存在 / 是另一个 flag（"-" 开头但不是单纯 "-"）→ stdin，不消费
  //   单独的 "-" → 显式 stdin 标记，消费它
  //   其它 → inline 值或 @file，消费它
  const readTextValue = (i) => {
    const next = args[i + 1];
    if (next === undefined) return { value: "-", advance: 0 };
    if (next === "-") return { value: "-", advance: 1 };
    if (next.startsWith("-")) return { value: "-", advance: 0 };
    return { value: next, advance: 1 };
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--schema") {
      schema = true;
    } else if (args[i] === "--top-k" && args[i + 1]) {
      topK = parseInt(args[++i], 10);
    } else if (args[i] === "--targets" && args[i + 1]) {
      targets = args[++i].split(",").map((t) => t.trim());
    } else if (args[i] === "--question") {
      hasQuestion = true;
      const v = readTextValue(i);
      question = v.value;
      i += v.advance;
    } else if (args[i] === "--cypher") {
      hasCypher = true;
      const v = readTextValue(i);
      cypher = v.value;
      i += v.advance;
    } else {
      console.error(`[query] 未知参数: ${args[i]}`);
      printUsage();
      process.exit(1);
    }
  }

  if (schema) return { schema: true };

  if (!hasQuestion && !hasCypher) {
    printUsage();
    process.exit(1);
  }
  if (hasQuestion && hasCypher) {
    console.error("[query] --question 与 --cypher 只能二选一");
    process.exit(1);
  }

  return {
    schema: false,
    question: hasQuestion ? question : null,
    cypher: hasCypher ? cypher : null,
    topK,
    targets,
  };
}

function printUsage() {
  console.error("Usage:");
  console.error("  node scripts/query.js --schema");
  console.error(
    '  node scripts/query.js --question "<问题>" [--top-k 5] [--targets 表,指标]'
  );
  console.error('  node scripts/query.js --cypher "<CYPHER>"');
  console.error("  # --question / --cypher 支持 inline / @file / -(stdin) 三态");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const parsed = parseArgs(process.argv);

  const config = loadConfig();
  const gc = config["graph-config"] || {};
  const envCfg = config.env || {};

  // --- Schema mode: print entities + relationships, no DB needed ---
  if (parsed.schema) {
    console.log(JSON.stringify(buildSchema(gc), null, 2));
    return;
  }

  const { question, cypher, topK, targets } = parsed;

  const neo4jUri = envCfg.NEO4J_URI || "bolt://localhost:7687";
  const neo4jDatabase = envCfg.NEO4J_DATABASE || "neo4j";
  const neo4jUser = envCfg.NEO4J_USER || "neo4j";
  const neo4jPassword = envCfg.NEO4J_PASSWORD;

  if (!neo4jPassword) {
    console.error(
      "[query] NEO4J_PASSWORD 未在 config.json 的 env 块中找到"
    );
    process.exit(1);
  }

  const driver = neo4j.driver(
    neo4jUri,
    neo4j.auth.basic(neo4jUser, neo4jPassword)
  );

  try {
    // --- Cypher mode ---
    if (cypher !== null) {
      const cypherText = await resolveText(cypher, "cypher");
      console.error(`[query] Cypher: ${cypherText}`);
      const rows = await runCypher(driver, neo4jDatabase, cypherText);
      console.log(JSON.stringify({ cypher: cypherText, rows }, null, 2));
      return;
    }

    // --- Vector search mode ---
    const modelPath =
      modelDirFromConfig(gc) || "scripts/pipeline/models/bge-small-zh-v1.5";

    const entities = gc.entities || {};
    const targetEntities = {};
    for (const [label, cfg] of Object.entries(entities)) {
      const hasVectorIndex = cfg.vector_index !== false;
      if (!hasVectorIndex) continue;
      if (targets && !targets.includes(label)) continue;
      targetEntities[label] = cfg;
    }

    const questionText = await resolveText(question, "question");

    console.error(`[query] Question: ${questionText}`);
    console.error(`[query] Top-K: ${topK}`);
    console.error(
      `[query] Targets: ${targets ? targets.join(", ") : "all vector-indexed"}`
    );
    console.error(
      `[query] Entities to search: ${Object.keys(targetEntities).join(", ")}`
    );

    // 直接用 PATH 上的 python；依赖见 scripts/pipeline/requirements.txt
    const pyPath = "python";

    const embedding = encodeQuestion(questionText, modelPath, pyPath);
    console.error(`[query] Embedding dimensions: ${embedding.length}`);

    const allResults = [];
    const relationships = Array.isArray(gc.relationships)
      ? gc.relationships
      : [];

    for (const label of Object.keys(targetEntities)) {
      const session = driver.session({ database: neo4jDatabase });
      try {
        const indexName = await findVectorIndexName(session, label);
        if (!indexName) {
          console.error(`[query] No vector index found for ${label}, skipping`);
          continue;
        }

        console.error(`[query] Searching ${label} (index: ${indexName})...`);

        const hits = await searchVectorIndex(
          session,
          indexName,
          label,
          embedding,
          topK
        );

        console.error(`[query]   Found ${hits.length} hits`);

        for (const hit of hits) {
          const cleanProps = cleanProperties(hit.properties);

          let graphContext = {};
          if (relationships.length > 0) {
            graphContext = await fetchGraphContext(
              session,
              label,
              hit.id,
              relationships
            );
          }

          allResults.push({
            label,
            score: hit.score,
            properties: cleanProps,
            context: graphContext,
          });
        }
      } finally {
        await session.close();
      }
    }

    allResults.sort((a, b) => b.score - a.score);

    const output = { question: questionText, results: allResults };
    console.log(JSON.stringify(output, null, 2));
  } finally {
    await driver.close();
  }
}

main().catch((err) => {
  console.error("[query] Fatal error:", err);
  process.exit(1);
});
