const API_BASE = 'http://localhost:8000';

class LakebaseClient {
  async queryLakebase(table = 'information_schema.tables') {
    const response = await fetch(`${API_BASE}/api/lakebase/query?table=${encodeURIComponent(table)}`);
    if (!response.ok) throw new Error('Failed to query Lakebase');
    return response.json();
  }

  async health() {
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
  }
}

export const client = new LakebaseClient();
