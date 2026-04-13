import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface SlackChannel {
  id: number;
  channel_id: string;
  channel_name: string;
  description: string;
  enabled: boolean;
  max_messages: number;
  created_at: string;
  updated_at: string;
}

interface ChannelForm {
  channel_id: string;
  channel_name: string;
  description: string;
  enabled: boolean;
  max_messages: number;
}

const EMPTY_FORM: ChannelForm = {
  channel_id: '',
  channel_name: '',
  description: '',
  enabled: true,
  max_messages: 50,
};

export default function SlackChannels() {
  const [channels, setChannels] = useState<SlackChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ChannelForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const data = await api.get<SlackChannel[]>('/slack-channels');
      setChannels(data);
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

  function openEdit(ch: SlackChannel) {
    setForm({
      channel_id: ch.channel_id,
      channel_name: ch.channel_name,
      description: ch.description,
      enabled: ch.enabled,
      max_messages: ch.max_messages,
    });
    setEditingId(ch.id);
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
        const updated = await api.put<SlackChannel>(`/slack-channels/${editingId}`, form);
        setChannels((prev) => prev.map((c) => (c.id === editingId ? updated : c)));
      } else {
        const created = await api.post<SlackChannel>('/slack-channels', form);
        setChannels((prev) => [...prev, created]);
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
      const updated = await api.patch<SlackChannel>(`/slack-channels/${id}/toggle`);
      setChannels((prev) => prev.map((c) => (c.id === id ? updated : c)));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Supprimer le canal « #${name} » ?`)) return;
    try {
      await api.delete(`/slack-channels/${id}`);
      setChannels((prev) => prev.filter((c) => c.id !== id));
    } catch (e: any) {
      setError(e.message);
    }
  }

  function set<K extends keyof ChannelForm>(key: K, value: ChannelForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  if (loading) return <div className="text-gray-400 animate-pulse">Chargement...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Canaux Slack</h1>
          <p className="text-sm text-gray-500 mt-1">
            Configurez les canaux Slack accessibles en lecture via le gateway MCP
          </p>
        </div>
        <button
          onClick={openNew}
          className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition"
        >
          + Ajouter un canal
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {/* Add/Edit form */}
      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {editingId ? 'Modifier le canal' : 'Ajouter un canal Slack'}
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  ID du canal Slack
                </label>
                <input
                  required
                  value={form.channel_id}
                  onChange={(e) => set('channel_id', e.target.value)}
                  placeholder="C01ABC2DEF3"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm font-mono"
                />
                <p className="text-xs text-gray-400 mt-1">
                  Trouvable dans les paramètres du canal Slack (ex: C01ABC2DEF3)
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Nom du canal
                </label>
                <input
                  required
                  value={form.channel_name}
                  onChange={(e) => set('channel_name', e.target.value)}
                  placeholder="general"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Description
              </label>
              <input
                value={form.description}
                onChange={(e) => set('description', e.target.value)}
                placeholder="Canal général de l'équipe"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Max messages par requête
                </label>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={form.max_messages}
                  onChange={(e) => set('max_messages', parseInt(e.target.value) || 50)}
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

      {/* Channel list */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 font-medium text-gray-600">Canal</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">ID Slack</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Description</th>
              <th className="text-center px-4 py-3 font-medium text-gray-600">Max msg</th>
              <th className="text-center px-4 py-3 font-medium text-gray-600">Activé</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {channels.map((ch) => (
              <tr key={ch.id} className="hover:bg-gray-50 transition">
                <td className="px-4 py-3">
                  <span className="font-medium text-gray-900">#{ch.channel_name}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-500">{ch.channel_id}</td>
                <td className="px-4 py-3 text-gray-600 truncate max-w-xs">
                  {ch.description || <span className="text-gray-300">—</span>}
                </td>
                <td className="px-4 py-3 text-center text-gray-600">{ch.max_messages}</td>
                <td className="px-4 py-3 text-center">
                  <button
                    onClick={() => handleToggle(ch.id)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
                      ch.enabled ? 'bg-primary-600' : 'bg-gray-300'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
                        ch.enabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => openEdit(ch)}
                    className="text-gray-400 hover:text-primary-600 transition mr-3"
                  >
                    Modifier
                  </button>
                  <button
                    onClick={() => handleDelete(ch.id, ch.channel_name)}
                    className="text-gray-400 hover:text-red-600 transition"
                  >
                    Supprimer
                  </button>
                </td>
              </tr>
            ))}
            {channels.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Aucun canal Slack configuré. Ajoutez-en un pour permettre la lecture via le gateway.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
