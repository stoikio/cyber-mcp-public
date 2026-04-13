import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import ConditionsEditor from '../components/ConditionsEditor';

type Conditions = Record<string, unknown>;

interface PolicyForm {
  name: string;
  description: string;
  tool_pattern: string;
  action: string;
  conditions: Conditions;
  enabled: boolean;
  priority: number;
}

const EMPTY: PolicyForm = {
  name: '',
  description: '',
  tool_pattern: '*',
  action: 'block',
  conditions: {},
  enabled: true,
  priority: 0,
};

export default function PolicyEdit() {
  const { id } = useParams();
  const isNew = !id;
  const navigate = useNavigate();
  const [form, setForm] = useState<PolicyForm>(EMPTY);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isNew) return;
    api
      .get<any>(`/policies/${id}`)
      .then((p) =>
        setForm({
          name: p.name,
          description: p.description,
          tool_pattern: p.tool_pattern,
          action: p.action,
          conditions: p.conditions ?? {},
          enabled: p.enabled,
          priority: p.priority,
        }),
      )
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, isNew]);

  function set<K extends keyof PolicyForm>(key: K, value: PolicyForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');

    const payload = {
      name: form.name,
      description: form.description,
      tool_pattern: form.tool_pattern,
      action: form.action,
      conditions: form.conditions,
      enabled: form.enabled,
      priority: form.priority,
    };

    setSaving(true);
    try {
      if (isNew) {
        await api.post('/policies', payload);
      } else {
        await api.put(`/policies/${id}`, payload);
      }
      navigate('/policies');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-gray-400 animate-pulse">Chargement...</div>;

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">
        {isNew ? 'Nouvelle politique' : `Modifier « ${form.name} »`}
      </h1>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nom</label>
            <input
              required
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pattern outil</label>
            <input
              required
              value={form.tool_pattern}
              onChange={(e) => set('tool_pattern', e.target.value)}
              placeholder="send_email, *, read_*"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm font-mono"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
          />
        </div>

        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Action</label>
            <select
              value={form.action}
              onChange={(e) => set('action', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            >
              <option value="block">block</option>
              <option value="warn">warn</option>
              <option value="log">log</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Priorité</label>
            <input
              type="number"
              value={form.priority}
              onChange={(e) => set('priority', parseInt(e.target.value) || 0)}
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
              <span className="text-sm text-gray-700">Activée</span>
            </label>
          </div>
        </div>

        <div className="border-t border-gray-100 pt-4">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">Conditions</h2>
          <ConditionsEditor
            value={form.conditions}
            onChange={(c) => set('conditions', c)}
          />
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white text-sm font-medium rounded-lg transition"
          >
            {saving ? 'Enregistrement...' : isNew ? 'Créer' : 'Enregistrer'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/policies')}
            className="px-5 py-2 text-sm text-gray-600 hover:text-gray-800 transition"
          >
            Annuler
          </button>
        </div>
      </form>
    </div>
  );
}
