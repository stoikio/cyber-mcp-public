import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface Integration {
  service: string;
  name: string;
  description: string;
  configured: boolean;
  mode: string;
  masked_value: string;
  label: string;
  updated_by: string;
  updated_at: string | null;
}

interface TestResult {
  service: string;
  status: string;
  message?: string;
  bot_name?: string;
  team?: string;
  type?: string;
}

const SERVICE_ICONS: Record<string, string> = {
  slack: '#',
  notion: 'N',
};

const SERVICE_PLACEHOLDER: Record<string, string> = {
  slack: 'xoxb-...',
  notion: 'ntn_...',
};

export default function Integrations() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editingService, setEditingService] = useState<string | null>(null);
  const [tokenValue, setTokenValue] = useState('');
  const [tokenLabel, setTokenLabel] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  async function load() {
    try {
      const data = await api.get<Integration[]>('/integrations');
      setIntegrations(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function startEdit(svc: string) {
    setEditingService(svc);
    setTokenValue('');
    setTokenLabel(integrations.find((i) => i.service === svc)?.label || '');
    setError('');
  }

  function cancelEdit() {
    setEditingService(null);
    setTokenValue('');
    setTokenLabel('');
  }

  async function handleSave(service: string) {
    if (!tokenValue.trim()) {
      setError('Le token ne peut pas être vide');
      return;
    }
    setError('');
    setSaving(true);
    try {
      const updated = await api.put<Integration>(`/integrations/${service}`, {
        value: tokenValue,
        label: tokenLabel,
      });
      setIntegrations((prev) => prev.map((i) => (i.service === service ? updated : i)));
      cancelEdit();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(service: string, name: string) {
    if (!confirm(`Supprimer le token ${name} ? L'intégration passera en mode mock.`)) return;
    try {
      await api.delete(`/integrations/${service}`);
      await load();
      setTestResults((prev) => {
        const next = { ...prev };
        delete next[service];
        return next;
      });
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleTest(service: string) {
    setTesting(service);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[service];
      return next;
    });
    try {
      const result = await api.post<TestResult>(`/integrations/${service}/test`);
      setTestResults((prev) => ({ ...prev, [service]: result }));
    } catch (e: any) {
      setTestResults((prev) => ({
        ...prev,
        [service]: { service, status: 'error', message: e.message },
      }));
    } finally {
      setTesting(null);
    }
  }

  if (loading) return <div className="text-gray-400 animate-pulse">Chargement...</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Intégrations</h1>
        <p className="text-sm text-gray-500 mt-1">
          Gérez les tokens d'accès aux services externes. Les tokens sont chiffrés (Fernet) en base de données.
        </p>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      <div className="grid gap-4">
        {integrations.map((integ) => {
          const isEditing = editingService === integ.service;
          const testResult = testResults[integ.service];

          return (
            <div
              key={integ.service}
              className="bg-white rounded-xl border border-gray-200 p-6"
            >
              <div className="flex items-start gap-4">
                {/* Icon */}
                <div
                  className={`flex items-center justify-center w-12 h-12 rounded-xl text-lg font-bold shrink-0 ${
                    integ.configured
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-gray-100 text-gray-400'
                  }`}
                >
                  {SERVICE_ICONS[integ.service] || integ.service[0].toUpperCase()}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3">
                    <h2 className="text-lg font-semibold text-gray-900">{integ.name}</h2>
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                        integ.configured
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {integ.configured ? 'Configuré' : 'Non configuré'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">{integ.description}</p>

                  {integ.configured && (
                    <div className="mt-3 flex items-center gap-4 text-sm">
                      <span className="font-mono text-gray-600 bg-gray-50 px-2 py-0.5 rounded">
                        {integ.masked_value}
                      </span>
                      {integ.label && (
                        <span className="text-gray-400">({integ.label})</span>
                      )}
                      {integ.updated_by && (
                        <span className="text-gray-400">
                          par {integ.updated_by}
                          {integ.updated_at && (
                            <> le {new Date(integ.updated_at).toLocaleDateString('fr-FR')}</>
                          )}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Test result */}
                  {testResult && (
                    <div
                      className={`mt-3 text-sm px-3 py-2 rounded-lg ${
                        testResult.status === 'ok'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-red-50 text-red-700 border border-red-200'
                      }`}
                    >
                      {testResult.status === 'ok' ? (
                        <>
                          Connexion réussie
                          {testResult.bot_name && <> — bot: <strong>{testResult.bot_name}</strong></>}
                          {testResult.team && <> ({testResult.team})</>}
                        </>
                      ) : (
                        <>Erreur : {testResult.message}</>
                      )}
                    </div>
                  )}

                  {/* Edit form */}
                  {isEditing && (
                    <div className="mt-4 space-y-3">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Nouveau token
                        </label>
                        <input
                          type="password"
                          value={tokenValue}
                          onChange={(e) => setTokenValue(e.target.value)}
                          placeholder={SERVICE_PLACEHOLDER[integ.service] || 'Token...'}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm font-mono"
                          autoFocus
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Libellé (optionnel)
                        </label>
                        <input
                          value={tokenLabel}
                          onChange={(e) => setTokenLabel(e.target.value)}
                          placeholder="ex: Bot production, Token lecture seule..."
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                        />
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleSave(integ.service)}
                          disabled={saving}
                          className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white text-sm font-medium rounded-lg transition"
                        >
                          {saving ? 'Enregistrement...' : 'Enregistrer'}
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition"
                        >
                          Annuler
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Actions */}
                {!isEditing && (
                  <div className="flex items-center gap-2 shrink-0">
                    {integ.configured && (
                      <button
                        onClick={() => handleTest(integ.service)}
                        disabled={testing === integ.service}
                        className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50 transition disabled:opacity-50"
                      >
                        {testing === integ.service ? 'Test...' : 'Tester'}
                      </button>
                    )}
                    <button
                      onClick={() => startEdit(integ.service)}
                      className="px-3 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition"
                    >
                      {integ.configured ? 'Modifier' : 'Configurer'}
                    </button>
                    {integ.configured && (
                      <button
                        onClick={() => handleDelete(integ.service, integ.name)}
                        className="px-3 py-1.5 text-sm border border-red-200 text-red-600 hover:bg-red-50 rounded-lg transition"
                      >
                        Supprimer
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
        <strong>Note :</strong> Après avoir modifié un token, vous devez redémarrer le gateway MCP
        pour que le changement prenne effet sur les outils exposés à Claude.
      </div>
    </div>
  );
}
