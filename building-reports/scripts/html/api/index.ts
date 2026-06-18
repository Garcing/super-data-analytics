import type { VercelRequest, VercelResponse } from '@vercel/node';

function getApiSecret(): string {
  return process.env.API_SECRET || '';
}

function validateAuth(req: VercelRequest): boolean {
  const auth = req.headers.authorization;
  const secret = getApiSecret();
  if (!secret) return false;
  return auth === `Bearer ${secret}`;
}

async function handleList(res: VercelResponse) {
  try {
    const { head } = await import('@vercel/blob');
    const blob = await head('reports-index.json');
    if (!blob || !blob.url) {
      return res.status(200).json({ reports: [] });
    }
    const fetchRes = await fetch(blob.url);
    const index = await fetchRes.json();
    return res.status(200).json(index);
  } catch {
    return res.status(200).json({ reports: [] });
  }
}

async function handleCreate(req: VercelRequest, res: VercelResponse) {
  if (!validateAuth(req)) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const body = req.body;
    const { id } = body;

    if (!id || !body.meta?.title) {
      return res.status(400).json({ error: 'Missing required fields: id, meta.title' });
    }

    const { put: blobPut, head } = await import('@vercel/blob');

    await blobPut(`reports/${id}.json`, JSON.stringify(body, null, 2), {
      access: 'public',
      addRandomSuffix: false,
    });

    let index: any = { reports: [] };
    try {
      const idxBlob = await head('reports-index.json');
      if (idxBlob && idxBlob.url) {
        const idxRes = await fetch(idxBlob.url);
        index = await idxRes.json();
      }
    } catch { /* empty index is fine */ }

    const overallText = body.summary?.overall || '';
    const summaryPreview = overallText.slice(0, 100) + (overallText.length > 100 ? '...' : '');
    const newEntry = {
      id,
      title: body.meta.title,
      created_at: body.meta.generated_at || new Date().toISOString(),
      summary_preview: summaryPreview,
      stats: {
        total_conclusions: body.summary?.total_conclusions || 0,
        high_importance: body.summary?.high_importance_count || 0,
      },
    };

    const existingIdx = index.reports.findIndex((r: any) => r.id === id);
    let updated = false;
    if (existingIdx >= 0) {
      index.reports.splice(existingIdx, 1);
      index.reports.unshift(newEntry);
      updated = true;
    } else {
      index.reports.unshift(newEntry);
    }

    await blobPut('reports-index.json', JSON.stringify(index, null, 2), {
      access: 'public',
      addRandomSuffix: false,
    });

    return res.status(200).json({ url: `/report/${id}`, updated });
  } catch (err: any) {
    return res.status(500).json({ error: 'Failed to save report', detail: err?.message || String(err) });
  }
}

async function handleGetOne(res: VercelResponse, id: string) {
  try {
    const { head } = await import('@vercel/blob');
    const key = `reports/${id}.json`;
    const blob = await head(key);
    if (!blob || !blob.url) {
      return res.status(404).json({ error: 'Report not found' });
    }
    const fetchRes = await fetch(blob.url);
    const report = await fetchRes.json();
    return res.status(200).json(report);
  } catch {
    return res.status(404).json({ error: 'Report not found' });
  }
}

async function handleDelete(req: VercelRequest, res: VercelResponse, id: string) {
  if (!validateAuth(req)) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const { del: blobDel, put: blobPut, head } = await import('@vercel/blob');
    await blobDel(`reports/${id}.json`);

    let index: any = { reports: [] };
    try {
      const idxBlob = await head('reports-index.json');
      if (idxBlob && idxBlob.url) {
        const idxRes = await fetch(idxBlob.url);
        index = await idxRes.json();
      }
    } catch { /* empty index is fine */ }

    index.reports = index.reports.filter((r: any) => r.id !== id);
    await blobPut('reports-index.json', JSON.stringify(index, null, 2), {
      access: 'public',
      addRandomSuffix: false,
    });

    return res.status(200).json({ success: true });
  } catch {
    return res.status(500).json({ error: 'Failed to delete report' });
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Parse the URL to extract path segments
  // /api/reports → list/create
  // /api/reports/:id → get/delete
  const url = new URL(req.url || '/', 'http://localhost');
  const pathParts = url.pathname.replace(/^\/api\/reports\/?/, '').split('/').filter(Boolean);

  if (pathParts.length === 0) {
    if (req.method === 'GET') return handleList(res);
    if (req.method === 'POST') return handleCreate(req, res);
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // Single path segment = report ID
  const reportId = decodeURIComponent(pathParts[0]);
  if (req.method === 'GET') return handleGetOne(res, reportId);
  if (req.method === 'DELETE') return handleDelete(req, res, reportId);
  return res.status(405).json({ error: 'Method not allowed' });
}
