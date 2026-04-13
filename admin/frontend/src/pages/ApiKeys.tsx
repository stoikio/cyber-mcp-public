import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../api/client';

interface ApiKeyRow {
  hash_prefix: string;
  email: string;
  created_at: string;
  expires_at: string | null;
  revoked: boolean;
}

interface CreatedKey {
  api_key: string;
  hash_prefix: string;
  email: string;
  expires_at: string | null;
}

export default function ApiKeys() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [email, setEmail] = useState('');
  const [days, setDays] = useState(180);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreatedKey | null>(null);

  async function load() {
    try {
      const data = await api.get<ApiKeyRow[]>('/api-keys');
      setKeys(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    setCreating(true);
    try {
      const result = await api.post<CreatedKey>('/api-keys', {
        email,
        expires_in_days: days,
      });
      setCreated(result);
      setShowCreate(false);
      setEmail('');
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(prefix: string) {
    if (!confirm(`Révoquer la clé ${prefix}... ?`)) return;
    try {
      await api.post(`/api-keys/${prefix}/revoke`);
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (loading) return <div className="text-gray-400 animate-pulse">Chargement...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Clés API</h1>
        <button
          onClick={() => { setShowCreate(true); setCreated(null); }}
          className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition"
        >
          + Nouvelle clé
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {/* Created key display */}
      {created && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 space-y-2">
          <div className="text-sm font-medium text-emerald-800">
            Clé créée pour {created.email}
          </div>
          <div className="text-sm text-emerald-700">
            Copiez cette clé maintenant, elle ne sera plus affichée :
          </div>
          <code className="block bg-white border border-emerald-300 rounded px-3 py-2 text-sm font-mono select-all break-all">
            {created.api_key}
          </code>
          <button
            onClick={() => setCreated(null)}
            className="text-xs text-emerald-600 hover:underline"
          >
            Fermer
          </button>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Créer une clé API</h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                className="w-full max-w-sm px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Expiration (jours)</label>
              <input
                type="number"
                min={1}
                max={730}
                value={days}
                onChange={(e) => setDays(parseInt(e.target.value) || 180)}
                className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={creating}
                className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white text-sm font-medium rounded-lg transition"
              >
                {creating ? 'Création...' : 'Créer'}
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Annuler
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 font-medium text-gray-600">Hash</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Email</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Créée</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Expire</th>
              <th className="text-center px-4 py-3 font-medium text-gray-600">Statut</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {keys.map((k) => (
              <tr key={k.hash_prefix + k.email} className="hover:bg-gray-50 transition">
                <td className="px-4 py-3 font-mono text-xs">{k.hash_prefix}...</td>
                <td className="px-4 py-3 text-gray-700">{k.email}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {new Date(k.created_at).toLocaleDateString('fr-FR')}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {k.expires_at
                    ? new Date(k.expires_at).toLocaleDateString('fr-FR')
                    : '—'}
                </td>
                <td className="px-4 py-3 text-center">
                  {k.revoked ? (
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                      Révoquée
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                      Active
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {!k.revoked && (
                    <button
                      onClick={() => handleRevoke(k.hash_prefix)}
                      className="text-gray-400 hover:text-red-600 transition text-sm"
                    >
                      Révoquer
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Aucune clé API
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
