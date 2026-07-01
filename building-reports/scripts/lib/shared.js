/**
 * building-reports 共享工具（lib/shared.js）
 * ============================================================================
 * 与 querying-data 同构的基建：凭证统一来自 config.json、代理感知、
 * 通用三态输入（inline / @file / stdin）、工作区产物目录约定。
 *
 * 设计原则（对齐 querying-data）：
 *   - 凭证唯一来源 = ~/.super-data-analytics/config.json 的 env 块；
 *     脚本不读 .env、不依赖环境变量导出。
 *   - 配置缺失/字段不全时抛明确错误，由 agent 引导补全后写回 config.json 再重试。
 *   - 产物落盘路径由各 CLI 自己决定（agent 构造），shared.js 不干预。
 */
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export const CONFIG_PATH = join(homedir(), '.super-data-analytics', 'config.json');

// 凭证/配置：config.json 是唯一来源。
// 把 credentialKeys 中存在于 config.env 的字段灌进 process.env，供后续 getConfig 读取。
export function loadConfig(credentialKeys) {
  let raw;
  try {
    raw = readFileSync(CONFIG_PATH, 'utf-8');
  } catch (err) {
    if (err.code === 'ENOENT') {
      throw new Error(
        `配置文件不存在: ${CONFIG_PATH}\n` +
        `请提供所需凭证（${credentialKeys.join(' / ')}），我会帮你写入 config.json 的 env 块后重试。`
      );
    }
    throw new Error(`读取配置失败 ${CONFIG_PATH}: ${err.message}`);
  }

  let cfg;
  try {
    cfg = JSON.parse(raw);
  } catch (err) {
    throw new Error(`解析配置失败 ${CONFIG_PATH}: ${err.message}`);
  }

  const env = cfg.env || {};
  for (const key of credentialKeys) {
    if (env[key] !== undefined) process.env[key] = String(env[key]);
  }
}

// 代理感知：原生 fetch 默认忽略 HTTPS_PROXY（与 Python requests 不同），
// 检测到代理时通过 undici 的 ProxyAgent 显式接管。返回 { proxyUrl, proxyConfigured }。
export async function setupProxy() {
  const proxyUrl =
    process.env.HTTPS_PROXY || process.env.https_proxy ||
    process.env.HTTP_PROXY || process.env.http_proxy ||
    process.env.ALL_PROXY || process.env.all_proxy;
  if (!proxyUrl) return { proxyUrl: null, proxyConfigured: false };
  try {
    const { ProxyAgent, setGlobalDispatcher } = await import('undici');
    setGlobalDispatcher(new ProxyAgent(proxyUrl));
    return { proxyUrl, proxyConfigured: true };
  } catch {
    return { proxyUrl, proxyConfigured: false };
  }
}

// 关闭代理连接池，避免 Windows 下 process.exit 时 undici 句柄未关触发 libuv 断言崩溃。
export async function closeProxy() {
  try {
    const { getGlobalDispatcher } = await import('undici');
    await getGlobalDispatcher().close();
  } catch { /* ignore */ }
}

// ---------- 通用三态输入（inline / @file / stdin），与 querying-data 的 --query 同构 ----------
// 把单个 flag 的值解析成内部 source：
//   不传 / null / '-' → stdin（管道；- 是 Unix 惯用的"显式 stdin"）
//   '@<path>'         → file
//   其他              → inline（直接内容）
export function parseInputFlag(value) {
  if (value === null || value === undefined || value === '-') return { source: 'stdin' };
  if (value.startsWith('@')) {
    const path = value.slice(1);
    if (!path) throw new Error('输入 @ 后需提供文件路径');
    return { source: 'file', path };
  }
  if (!value) throw new Error('输入不能为空');
  return { source: 'inline', content: value };
}

export function readContentFile(filePath, { label = '输入' } = {}) {
  let content;
  try {
    content = readFileSync(filePath, 'utf-8').trim();
  } catch (e) {
    throw new Error(`无法读取${label}文件 ${filePath}: ${e.message}`);
  }
  if (!content) throw new Error(`${label}文件为空: ${filePath}`);
  return content;
}

// 非 TTY（脚本/管道/agent 子进程）里，若调用方忘了带输入且 stdin 没关闭，
// for-await 会永久挂起。加一个首字节超时：到点没收完就主动报错退出，不再卡死。
export async function readContentFromStdin(stream = process.stdin, { label = '输入', timeoutMs } = {}) {
  if (typeof stream.setEncoding === 'function') stream.setEncoding('utf8');

  const timeout = Number(timeoutMs ?? process.env.SDA_STDIN_TIMEOUT_MS ?? 15_000);

  const readPromise = (async () => {
    let content = '';
    for await (const chunk of stream) content += chunk;
    return content.trim();
  })();

  let timer;
  const timeoutPromise = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('STDIN_READ_TIMEOUT')), timeout);
  });

  let content;
  try {
    content = await Promise.race([readPromise, timeoutPromise]);
  } catch (err) {
    if (stream.destroy) stream.destroy();
    if (err && err.message === 'STDIN_READ_TIMEOUT') {
      throw new Error(
        `等待 stdin 超时（${timeout / 1000}s 内未收到${label}）。\n` +
        '常见原因：在非交互环境（脚本/管道/agent）里既没传 inline / @文件，stdin 也没关闭。\n' +
        '解决：用显式输入传入，或确保管道写完后关闭 stdin。'
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!content) throw new Error(`stdin 中的${label}为空`);
  return content;
}

export async function readContentSource(options, stream = process.stdin, opts = {}) {
  if (options.source === 'stdin') return readContentFromStdin(stream, opts);
  if (options.source === 'file') return readContentFile(options.path, opts);
  const content = options.content.trim();
  if (!content) throw new Error(`inline ${opts.label || '输入'} 为空`);
  return content;
}

// ---------- 通用乐观锁写（搭配 Blob 的 ifMatch） ----------
// 用于"读索引 → 改 → 写回"场景，防止并发/陈旧读导致的丢失更新。
// 关键：read 必须强一致（带 token 走 SDK get()，不要走公开 URL 的 CDN），
//       返回 { data, etag }；write 用 ifMatch=etag 落盘，不匹配就退避重试。
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function isPreconditionFailed(err) {
  if (!err) return false;
  if (err.name === 'BlobPreconditionFailedError') return true;
  return /precondition|if[-_]match|412/i.test(String(err.message || err));
}

/**
 * @param {object}  opts
 * @param {() => Promise<{data: any, etag?: string}>} opts.read  读当前状态 + etag（强一致）
 * @param {(data: any) => any|Promise<any>}            opts.modify 在当前 data 上算出下一个状态
 * @param {(next: any, etag?: string) => Promise<void>} opts.write 带 ifMatch 落盘
 * @param {number} [opts.attempts=5]
 */
export async function withOptimisticLock({ read, modify, write, attempts = 5, baseDelay = 300 }) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    const { data, etag } = await read();
    const next = await modify(data);
    try {
      await write(next, etag);
      return next;
    } catch (err) {
      lastErr = err;
      if (!isPreconditionFailed(err) || i === attempts - 1) throw err;
      await sleep(baseDelay * (i + 1) + Math.random() * baseDelay);
    }
  }
  throw lastErr;
}

