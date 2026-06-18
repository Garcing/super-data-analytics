#!/usr/bin/env node
/**
 * query.js — Node.js vector search + graph expansion CLI for GraphRAG
 *
 * Usage:
 *   node query.js "用户问题" [--top-k 5] [--targets 表,指标]
 *
 * Flow:
 *   1. Encode question via Python embedding subprocess
 *   2. Search Neo4j vector indexes for each target entity
 *   3. Expand graph context via relationships
 *   4. Output JSON to stdout (logs go to stderr)
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import neo4j from "neo4j-driver";

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = resolve(__dirname, "..");

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
// 1. Config loading
// ---------------------------------------------------------------------------

/**
 * Simple KEY=VALUE .env parser (no dotenv dependency).
 */
function loadEnv(envPath) {
  const env = {};
  try {
    const content = readFileSync(envPath, "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eqIndex = trimmed.indexOf("=");
      if (eqIndex === -1) continue;
      const key = trimmed.slice(0, eqIndex).trim();
      const value = trimmed.slice(eqIndex + 1).trim();
      env[key] = value;
    }
  } catch {
    console.error(`Warning: could not read ${envPath}`);
  }
  return env;
}

/**
 * Minimal YAML parser for graph-config.yaml.
 * Only supports flat key-value, one-level nested maps, and simple list-of-maps.
 * Sufficient for our config structure.
 */
function parseGraphConfig(configPath) {
  const content = readFileSync(configPath, "utf-8");
  const lines = content.split("\n");

  const root = {};
  let currentSection = null;
  let currentEntity = null;
  let inEntities = false;
  let inRelationships = false;
  let currentRel = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\t/g, "  "); // normalize tabs to spaces
    const trimmed = line.trim();

    // Skip empty and comment lines
    if (!trimmed || trimmed.startsWith("#")) continue;

    const indent = line.length - line.trimStart().length;

    // Top-level sections
    if (indent === 0 && trimmed.endsWith(":") && !trimmed.startsWith("-")) {
      const sectionName = trimmed.slice(0, -1).trim();
      currentSection = sectionName;
      inEntities = sectionName === "entities";
      inRelationships = sectionName === "relationships";
      currentEntity = null;
      currentRel = null;

      if (!root[sectionName]) {
        root[sectionName] = inEntities || inRelationships ? {} : {};
      }
      continue;
    }

    // --- entities section ---
    if (inEntities && indent === 2 && !trimmed.startsWith("-")) {
      // Entity label as key
      if (trimmed.endsWith(":")) {
        const entityLabel = trimmed.slice(0, -1).trim();
        currentEntity = entityLabel;
        root.entities[entityLabel] = {};
      }
      continue;
    }

    if (inEntities && indent === 4 && currentEntity) {
      const colonIdx = trimmed.indexOf(":");
      if (colonIdx !== -1) {
        const key = trimmed.slice(0, colonIdx).trim();
        const val = trimmed.slice(colonIdx + 1).trim();
        if (key === "vector_index") {
          root.entities[currentEntity][key] = val !== "false";
        } else {
          root.entities[currentEntity][key] = val;
        }
      }
      continue;
    }

    // --- relationships section ---
    if (inRelationships && trimmed.startsWith("- type:")) {
      const colonIdx = trimmed.indexOf(":", trimmed.indexOf("type") + 4);
      const relType = trimmed.slice(colonIdx + 1).trim();
      currentRel = { type: relType, match: {} };
      if (!root.relationships._list) root.relationships._list = [];
      root.relationships._list.push(currentRel);
      continue;
    }

    if (inRelationships && currentRel) {
      if (indent === 4) {
        const colonIdx = trimmed.indexOf(":");
        if (colonIdx !== -1) {
          const key = trimmed.slice(0, colonIdx).trim();
          const val = trimmed.slice(colonIdx + 1).trim();
          if (key === "match") {
            // match is a sub-map, handled at indent 6
          } else if (key === "via" || key === "properties") {
            // Skip for now, not needed for query expansion
          } else {
            currentRel[key] = val;
          }
        }
      }
      if (indent === 6) {
        const colonIdx = trimmed.indexOf(":");
        if (colonIdx !== -1) {
          const key = trimmed.slice(0, colonIdx).trim();
          const val = trimmed.slice(colonIdx + 1).trim();
          currentRel.match[key] = val;
        }
      }
    }

    // --- other top-level sections (neo4j, embedding, feishu) ---
    if (
      currentSection &&
      !inEntities &&
      !inRelationships &&
      indent === 2 &&
      !trimmed.startsWith("-")
    ) {
      const colonIdx = trimmed.indexOf(":");
      if (colonIdx !== -1) {
        const key = trimmed.slice(0, colonIdx).trim();
        const val = trimmed.slice(colonIdx + 1).trim();
        if (!root[currentSection]) root[currentSection] = {};
        root[currentSection][key] = val;
      }
    }
  }

  // Convert relationships from _list to array
  if (root.relationships && root.relationships._list) {
    root.relationships = root.relationships._list;
  }

  return root;
}

// ---------------------------------------------------------------------------
// 2. Encode question via Python subprocess
// ---------------------------------------------------------------------------

/**
 * Call Python embedding.py to encode text into a vector.
 * Returns a float array.
 */
function encodeQuestion(text, modelPath, pythonPath) {
  const scriptPath = join(PROJECT_ROOT, "sync", "embedding.py");
  const absModelPath = resolve(PROJECT_ROOT, modelPath);

  console.error(`[query] Encoding question via Python...`);
  console.error(`[query]   python: ${pythonPath}`);
  console.error(`[query]   script: ${scriptPath}`);
  console.error(`[query]   model:  ${absModelPath}`);

  let stdout;
  try {
    const buffer = execFileSync(pythonPath, [
      scriptPath,
      "encode",
      text,
      "--model-path",
      absModelPath,
    ], {
      encoding: "utf-8",
      shell: true,
      timeout: 60000,
    });
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
// 3. Vector index search
// ---------------------------------------------------------------------------

/**
 * Discover the actual vector index name for a given label from the database.
 * Returns the index name or null if not found.
 */
async function findVectorIndexName(session, label) {
  try {
    const result = await session.run("SHOW VECTOR INDEXES YIELD name, labelsOrTypes");
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

/**
 * Search a vector index for the given label.
 * Returns array of { id, score, properties }.
 */
async function searchVectorIndex(session, indexName, label, embedding, topK) {
  const escLabel = label.replace(/`/g, "``");

  // db.index.vector.queryNodes takes index name as a string parameter,
  // not a backtick-escaped identifier.
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
// 4. Graph context expansion
// ---------------------------------------------------------------------------

/**
 * For a given node, expand graph context by following relationships.
 * Returns an object keyed by related entity label, each value is an
 * array of property objects.
 */
async function fetchGraphContext(
  session,
  label,
  keyField,
  keyFieldValue,
  relationships
) {
  const context = {};
  const escLabel = label.replace(/`/g, "``");

  // Find all relationships that involve this label
  const relevantRels = relationships.filter(
    (rel) => rel.from === label || rel.to === label
  );

  for (const rel of relevantRels) {
    const isSource = rel.from === label;
    const otherLabel = isSource ? rel.to : rel.from;

    const escOther = otherLabel.replace(/`/g, "``");
    const escRelType = rel.type.replace(/`/g, "``");

    // Determine direction and match field
    let cypher;
    if (isSource) {
      // (this)-[r]->(other)  where this.match.source_field == other.match.target_field
      const srcField = rel.match.source_field;
      const tgtField = rel.match.target_field;
      const escSrcField = srcField;
      const escTgtField = tgtField;

      // Handle self-referencing (e.g., 表-关联-表 via edge table)
      if (rel.from === rel.to && rel.via) {
        // Self-referencing with via table: skip for context expansion
        // (these use separate edge nodes, handled differently)
        continue;
      }

      cypher = `
        MATCH (n:\`${escLabel}\`)-[:\`${escRelType}\`]->(other:\`${escOther}\`)
        WHERE n.\`${escSrcField}\` = $keyValue
        RETURN properties(other) AS props
        LIMIT 20
      `;
    } else {
      // (other)-[r]->(this)
      const srcField = rel.match.source_field;
      const tgtField = rel.match.target_field;
      const escSrcField = srcField;
      const escTgtField = tgtField;

      cypher = `
        MATCH (other:\`${escOther}\`)-[:\`${escRelType}\`]->(n:\`${escLabel}\`)
        WHERE n.\`${escTgtField}\` = $keyValue
        RETURN properties(other) AS props
        LIMIT 20
      `;
    }

    try {
      const result = await session.run(cypher, { keyValue: keyFieldValue });

      if (result.records.length > 0) {
        if (!context[otherLabel]) context[otherLabel] = [];

        for (const record of result.records) {
          const rawProps = record.get("props");
          const cleanProps = {};
          for (const [k, v] of Object.entries(rawProps)) {
            if (!INTERNAL_PROPS.has(k)) {
              cleanProps[k] = v;
            }
          }
          context[otherLabel].push(cleanProps);
        }
      }
    } catch (err) {
      console.error(
        `[query] Graph expansion failed for ${label}->${otherLabel}: ${err.message}`
      );
    }
  }

  return context;
}

// ---------------------------------------------------------------------------
// 5. Cypher query mode
// ---------------------------------------------------------------------------

/**
 * Run a raw Cypher query and return results as JSON.
 * Used for count, list, filter, graph traversal questions
 * that vector search can't handle.
 */
async function runCypher(driver, database, cypher, params = {}) {
  const session = driver.session({ database });
  try {
    const result = await session.run(cypher, params);
    const rows = result.records.map((record) => {
      const obj = {};
      for (const key of record.keys) {
        let val = record.get(key);

        // Clean Neo4j integers to JS numbers
        if (neo4j.isInt(val)) {
          val = val.toNumber();
        }

        // Clean node properties
        if (val && typeof val === "object" && val.properties) {
          val = cleanProperties(val.properties);
        }

        // Clean list of nodes
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
// 6. CLI argument parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = argv.slice(2);
  let question = null;
  let topK = 5;
  let targets = null;
  let cypher = null;
  let cypherParams = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--top-k" && args[i + 1]) {
      topK = parseInt(args[++i], 10);
    } else if (args[i] === "--targets" && args[i + 1]) {
      targets = args[++i].split(",").map((t) => t.trim());
    } else if (args[i] === "--cypher" && args[i + 1]) {
      cypher = args[++i];
    } else if (args[i] === "--params" && args[i + 1]) {
      cypherParams = JSON.parse(args[++i]);
    } else if (!args[i].startsWith("-")) {
      question = args[i];
    }
  }

  if (!question && !cypher) {
    console.error("Usage:");
    console.error("  node query.js \"用户问题\" [--top-k 5] [--targets 表,指标]");
    console.error("  node query.js --cypher \"MATCH ... RETURN ...\" [--params '{}']");
    process.exit(1);
  }

  return { question, topK, targets, cypher, cypherParams };
}

// ---------------------------------------------------------------------------
// 6. Clean properties helper
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
// Main
// ---------------------------------------------------------------------------

async function main() {
  const { question, topK, targets, cypher, cypherParams } = parseArgs(process.argv);

  // Load config
  const env = loadEnv(join(PROJECT_ROOT, ".env"));
  const config = parseGraphConfig(join(PROJECT_ROOT, "graph-config.yaml"));

  const neo4jUri = config.neo4j?.uri || "bolt://localhost:7687";
  const neo4jDatabase = config.neo4j?.database || "neo4j";
  const neo4jUser = env.NEO4J_USER || "neo4j";
  const neo4jPassword = env.NEO4J_PASSWORD;

  if (!neo4jPassword) {
    console.error("[query] NEO4J_PASSWORD not found in .env");
    process.exit(1);
  }

  const driver = neo4j.driver(
    neo4jUri,
    neo4j.auth.basic(neo4jUser, neo4jPassword)
  );

  try {
    // --- Cypher mode ---
    if (cypher) {
      console.error(`[query] Cypher: ${cypher}`);
      const rows = await runCypher(driver, neo4jDatabase, cypher, cypherParams || {});
      console.log(JSON.stringify({ cypher, rows }, null, 2));
      return;
    }

    // --- Vector search mode (default) ---
    const modelPath =
      config.embedding?.model_path ||
      "sync/models/bge-small-zh-v1.5";

    // Determine which entities to search
    const entities = config.entities || {};
    const targetEntities = {};
    for (const [label, cfg] of Object.entries(entities)) {
      const hasVectorIndex = cfg.vector_index !== false;
      if (!hasVectorIndex) continue;
      if (targets && !targets.includes(label)) continue;
      targetEntities[label] = cfg;
    }

    console.error(`[query] Question: ${question}`);
    console.error(`[query] Top-K: ${topK}`);
    console.error(
      `[query] Targets: ${targets ? targets.join(", ") : "all vector-indexed"}`
    );
    console.error(
      `[query] Entities to search: ${Object.keys(targetEntities).join(", ")}`
    );

    // Resolve Python interpreter path
    const pythonPath = env.PYTHON_PATH || "python";

    // Step 1: Encode question
    const embedding = encodeQuestion(question, modelPath, pythonPath);
    console.error(`[query] Embedding dimensions: ${embedding.length}`);

    // Step 2: Connect to Neo4j
    const allResults = [];

    const relationships = Array.isArray(config.relationships)
      ? config.relationships
      : [];

    // Step 3: Discover vector index names and search
    for (const [label, cfg] of Object.entries(targetEntities)) {
      const keyField = cfg.key_field;

      const session = driver.session({ database: neo4jDatabase });
      try {
        // Discover the actual index name for this label
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
          const keyFieldValue = cleanProps[keyField];

          // Step 4: Expand graph context
          let graphContext = {};
          if (keyFieldValue && relationships.length > 0) {
            graphContext = await fetchGraphContext(
              session,
              label,
              keyField,
              keyFieldValue,
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

    // Step 5: Sort by score descending
    allResults.sort((a, b) => b.score - a.score);

    // Step 6: Output JSON
    const output = {
      question,
      results: allResults,
    };

    console.log(JSON.stringify(output, null, 2));
  } finally {
    await driver.close();
  }
}

main().catch((err) => {
  console.error("[query] Fatal error:", err);
  process.exit(1);
});
