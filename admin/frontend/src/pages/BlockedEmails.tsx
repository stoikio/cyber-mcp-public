import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface BlockedPattern {
  id: number;
  pattern: string;
  description: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface PatternForm {
  pattern: string;
  description: string;
  enabled: boolean;
}

const EMPTY_FORM: PatternForm = {
  pattern: '',
  description: '',
  enabled: true,
};

export default function BlockedEmails() {
  const [patterns, setPatterns] = useState<BlockedPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<PatternForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [testResult, setTestResult] = useState<null | boolean>(null);

  async function load() {
    try {
      const data = await api.get<BlockedPattern[]>('/blocked-emails');
      setPatterns(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function openNew() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowForm(true);
    setError('');
  }

  function openEdit(p: BlockedPattern) {
    setForm({
      pattern: p.pattern,
      description: p.description,
      enabled: p.enabled,
    });
    setEditingId(p.id);
    setShowForm(true);
    setError('');
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setError('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      if (editingId) {
        const updated = await api.put<BlockedPattern>(`/blocked-emails/${editingId}`, form);
        setPatterns((prev) => prev.map((p) => (p.id === editingId ? updated : p)));
      } else {
        const created = await api.post<BlockedPattern>('/blocked-emails', form);
        setPatterns((prev) => [...prev, created]);
      }
      closeForm();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(id: number) {
    try {
      const updated = await api.patch<BlockedPattern>(`/blocked-emails/${id}/toggle`);
      setPatterns((prev) => prev.map((p) => (p.id === id ? updated : p)));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: number, pattern: string) {
    if (!confirm(`Supprimer le pattern « ${pattern} » ?`)) return;
    try {
      await api.delete(`/blocked-emails/${id}`);
      setPatterns((prev) => prev.filter((p) => p.id !== id));
    } catch (e: any) {
      setError(e.message);
    }
  }

  function handleTest() {
    if (!testEmail) return;
    const enabled = patterns.filter((p) => p.enabled);
    const blocked = enabled.some((p) => {
      try {
        return new RegExp(p.pattern, 'i').test(testEmail);
      } catch {
        return false;
      }
    });
    setTestResult(blocked);
  }

  function set<K extends keyof PatternForm>(key: K, value: PatternForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  if (loading) return <div className="text-gray-400 animate-pulse">Chargement...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Comptes bloqués</h1>
          <p className="text-sm text-gray-500 mt-1">
            Patterns regex d'emails interdits de connexion au gateway MCP (JWT, API key, OAuth)
          </p>
        </div>
        <button
          onClick={openNew}
          className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition"
        >
          + Ajouter un pattern
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {/* Test tool */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-2">Tester un email</h2>
        <div className="flex gap-3 items-center">
          <input
            type="email"
            value={testEmail}
            onChange={(e) => { setTestEmail(e.target.value); setTestResult(null); }}
            placeholder="admin.service@example.com"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
          />
          <button
            onClick={handleTest}
            disabled={!testEmail}
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 disabled:bg-gray-50 disabled:text-gray-300 text-sm font-medium text-gray-700 rounded-lg transition"
          >
            Tester
          </button>
          {testResult !== null && (
            <span className={`text-sm font-medium ${testResult ? 'text-red-600' : 'text-green-600'}`}>
              {testResult ? 'Bloqué' : 'Autorisé'}
            </span>
          )}
        </div>
      </div>

      {/* Add/Edit form */}
      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {editingId ? 'Modifier le pattern' : 'Ajouter un pattern bloqué'}
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Pattern (regex)
              </label>
              <input
                required
                value={form.pattern}
                onChange={(e) => set('pattern', e.target.value)}
                placeholder="^admin\..*@example\.com$"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm font-mono"
              />
              <p className="text-xs text-gray-400 mt-1">
                Expression régulière Python (case-insensitive). Sera évaluée avec <code>re.search()</code>.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Description
              </label>
              <input
                value={form.description}
                onChange={(e) => set('description', e.target.value)}
                placeholder="Administrative accounts (admin.*@example.com)"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>

            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => set('enabled', e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Activé</span>
              </label>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white text-sm font-medium rounded-lg transition"
              >
                {saving ? 'Enregistrement...' : editingId ? 'Enregistrer' : 'Ajouter'}
              </button>
              <button
                type="button"
                onClick={closeForm}
                className="px-5 py-2 text-sm text-gray-600 hover:text-gray-800 transition"
              >
                Annuler
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Pattern list */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 font-medium text-gray-600">Pattern</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Description</th>
              <th className="text-center px-4 py-3 font-medium text-gray-600">Activé</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {patterns.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50 transition">
                <td className="px-4 py-3">
                  <code className="text-sm font-mono text-gray-900 bg-gray-100 px-2 py-0.5 rounded">
                    {p.pattern}
                  </code>
                </td>
                <td className="px-4 py-3 text-gray-600 truncate max-w-xs">
                  {p.description || <span className="text-gray-300">—</span>}
                </td>
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
                  <button
                    onClick={() => openEdit(p)}
                    className="text-gray-400 hover:text-primary-600 transition mr-3"
                  >
                    Modifier
                  </button>
                  <button
                    onClick={() => handleDelete(p.id, p.pattern)}
                    className="text-gray-400 hover:text-red-600 transition"
                  >
                    Supprimer
                  </button>
                </td>
              </tr>
            ))}
            {patterns.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                  Aucun pattern bloqué configuré. Tous les comptes du domaine autorisé peuvent se connecter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
