import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface OAuthClient {
  client_id: string;
  client_name: string;
  redirect_uris: string[];
  grant_types: string[];
  created_at: string;
}

export default function OAuthClients() {
  const [clients, setClients] = useState<OAuthClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api
      .get<OAuthClient[]>('/oauth-clients')
      .then(setClients)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-400 animate-pulse">Chargement...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">OAuth Clients</h1>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 font-medium text-gray-600">Client ID</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Nom</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Redirect URIs</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Grant Types</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Créé</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {clients.map((c) => (
              <tr key={c.client_id} className="hover:bg-gray-50 transition">
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{c.client_id}</td>
                <td className="px-4 py-3 text-gray-700 font-medium">{c.client_name}</td>
                <td className="px-4 py-3">
                  <div className="space-y-0.5">
                    {(Array.isArray(c.redirect_uris) ? c.redirect_uris : []).map((uri, i) => (
                      <div key={i} className="text-xs text-gray-500 font-mono truncate max-w-xs">
                        {uri}
                      </div>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {(Array.isArray(c.grant_types) ? c.grant_types : []).join(', ')}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {new Date(c.created_at).toLocaleDateString('fr-FR')}
                </td>
              </tr>
            ))}
            {clients.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Aucun client OAuth enregistré
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
