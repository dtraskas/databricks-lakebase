class LakebaseClient {
  async getLakebaseData(table = 'information_schema.tables') {
    const response = await fetch(`/api/lakebase/data?table=${encodeURIComponent(table)}`);
    if (!response.ok) throw new Error(`Failed to fetch Lakebase data: ${response.status}`);
    return response.json();
  }

  async health() {
    const response = await fetch('/health');
    if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
    return response.json();
  }
}

export const client = new LakebaseClient();
