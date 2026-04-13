import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

interface Policy {
  id: number;
  name: string;
  description: string;
  tool_pattern: string;
  action: string;
  conditions: Record<string, unknown>;
  enabled: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

const ACTION_BADGE: Record<string, string> = {
  block: 'bg-red-100 text-red-700',
  warn: 'bg-amber-100 text-amber-700',
  log: 'bg-blue-100 text-blue-700',
};

export default function Policies() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load() {
    try {
      const data = await api.get<Policy[]>('/policies');
      setPolicies(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleToggle(id: number) {
    try {
      const updated = await api.patch<Policy>(`/policies/${id}/toggle`);
      setPolicies((prev) => prev.map((p) => (p.id === id ? updated : p)));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Supprimer la politique « ${name} » ?`)) return;
    try {
      await api.delete(`/policies/${id}`);
      setPolicies((prev) => prev.filter((p) => p.id !== id));
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (loading) return <div className="text-gray-400 animate-pulse">Chargement...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Politiques de sécurité</h1>
        <Link
          to="/policies/new"
          className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition"
        >
          + Nouvelle politique
        </Link>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 font-medium text-gray-600">Nom</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Pattern</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Action</th>
              <th className="text-center px-4 py-3 font-medium text-gray-600">Priorité</th>
              <th className="text-center px-4 py-3 font-medium text-gray-600">Activée</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {policies.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50 transition">
                <td className="px-4 py-3">
                  <Link to={`/policies/${p.id}`} className="font-medium text-primary-600 hover:underline">
                    {p.name}
                  </Link>
                  {p.description && (
                    <div className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{p.description}</div>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{p.tool_pattern}</td>
                <td className="px-4 py-3">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_BADGE[p.action] || 'bg-gray-100 text-gray-600'}`}>
                    {p.action}
                  </span>
                </td>
                <td className="px-4 py-3 text-center text-gray-600">{p.priority}</td>
                <td className="px-4 py-3 text-center">
                  <button
                    onClick={() => handleToggle(p.id)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
                      p.enabled ? 'bg-primary-600' : 'bg-gray-300'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
                        p.enabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    to={`/policies/${p.id}`}
                    className="text-gray-400 hover:text-primary-600 transition mr-3"
                  >
                    Modifier
                  </Link>
                  <button
                    onClick={() => handleDelete(p.id, p.name)}
                    className="text-gray-400 hover:text-red-600 transition"
                  >
                    Supprimer
                  </button>
                </td>
              </tr>
            ))}
            {policies.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Aucune politique configurée
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
