import { useState, useEffect } from 'react';
import { client } from './api';

function App() {
  const [queryResult, setQueryResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetchHealth();
    fetchLakebaseData();
  }, []);

  const fetchHealth = async () => {
    try {
      const result = await client.health();
      setHealth(result);
    } catch (err) {
      setError(err.message);
    }
  };

  const fetchLakebaseData = async (table = 'information_schema.tables') => {
    try {
      setLoading(true);
      setError(null);
      const result = await client.getLakebaseData(table);
      setQueryResult(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <header className="bg-white shadow-sm">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-4xl font-bold text-gray-900">Lakebase Connection</h1>
          <p className="text-gray-600 mt-1">PostgreSQL via OAuth Tokens</p>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            ⚠️ {error}
          </div>
        )}

        <div className="grid gap-6 md:grid-cols-2 mb-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Server Status</h2>
            {health ? (
              <div className="flex items-center gap-3">
                <div className="h-4 w-4 bg-green-500 rounded-full"></div>
                <span className="text-green-600 font-medium">Connected</span>
              </div>
            ) : (
              <p className="text-gray-500">Loading...</p>
            )}
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Query Tables</h2>
            <button
              onClick={() => fetchLakebaseData('information_schema.tables')}
              className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition"
            >
              Refresh Data
            </button>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Query Results</h2>
          {loading ? (
            <div className="text-center py-8">
              <p className="text-gray-500">Loading...</p>
            </div>
          ) : queryResult?.data ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-100 border-b">
                  <tr>
                    {queryResult.columns?.map((col) => (
                      <th key={col} className="px-4 py-2 text-left font-semibold text-gray-700">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {queryResult.data?.slice(0, 10).map((row, idx) => (
                    <tr key={idx} className="border-b hover:bg-gray-50">
                      {queryResult.columns?.map((col) => (
                        <td key={col} className="px-4 py-2 text-gray-600">
                          {String(row[col] || '').substring(0, 50)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-sm text-gray-500 mt-4">
                Showing {Math.min(10, queryResult.data?.length || 0)} of {queryResult.data?.length || 0} results
              </p>
            </div>
          ) : queryResult?.error ? (
            <p className="text-red-600">{queryResult.error}</p>
          ) : (
            <p className="text-gray-500">No data loaded yet</p>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
