import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface AuditEvent {
  id: number;
  ts: string;
  event: string;
  user_email: string;
  tool: string;
  details: Record<string, unknown>;
  ip: string;
}
interface AuditPage {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

const EVENT_TYPES = [
  '', 'TOOL_CALL', 'TOOL_OK', 'BLOCKED', 'POLICY_BLOCKED', 'POLICY_CAPPED',
  'RATE_LIMITED', 'EMAIL_SENT', 'DRAFT_CREATED', 'SLACK_SENT', 'SLACK_DM_SENT',
  'AUTH_FAILED', 'AUTH_EXPIRED', 'AUTH_RATE_LIMITED', 'AUTH_DOMAIN_REJECTED',
  'OAUTH_AUTHORIZED', 'OAUTH_TOKEN_ISSUED',
];

const EVENT_COLORS: Record<string, string> = {
  TOOL_CALL: 'bg-blue-100 text-blue-700',
  TOOL_OK: 'bg-green-100 text-green-700',
  BLOCKED: 'bg-red-100 text-red-700',
  POLICY_BLOCKED: 'bg-red-100 text-red-700',
  RATE_LIMITED: 'bg-amber-100 text-amber-700',
  EMAIL_SENT: 'bg-emerald-100 text-emerald-700',
  AUTH_FAILED: 'bg-rose-100 text-rose-700',
};

const PAGE_SIZE = 50;

export default function AuditLogs() {
  const [page, setPage] = useState<AuditPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);

  const [event, setEvent] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [tool, setTool] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [offset, setOffset] = useState(0);

  async function load(newOffset = offset) {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (event) params.set('event', event);
      if (userEmail) params.set('user_email', userEmail);
      if (tool) params.set('tool', tool);
      if (dateFrom) params.set('date_from', new Date(dateFrom).toISOString());
      if (dateTo) params.set('date_to', new Date(dateTo).toISOString());
      params.set('limit', String(PAGE_SIZE));
      params.set('offset', String(newOffset));

      const data = await api.get<AuditPage>(`/audit?${params}`);
      setPage(data);
      setOffset(newOffset);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(0); }, []);

  function handleFilter() {
    setExpanded(null);
    load(0);
  }

  const totalPages = page ? Math.ceil(page.total / PAGE_SIZE) : 0;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Journal d'audit</h1>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Type</label>
            <select
              value={event}
              onChange={(e) => setEvent(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary-500"
            >
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t}>{t || 'Tous'}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Utilisateur</label>
            <input
              value={userEmail}
              onChange={(e) => setUserEmail(e.target.value)}
              placeholder="email..."
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary-500 w-48"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Outil</label>
            <input
              value={tool}
              onChange={(e) => setTool(e.target.value)}
              placeholder="send_email..."
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary-500 w-40"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">De</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">À</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <button
            onClick={handleFilter}
            className="px-4 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition"
          >
            Filtrer
          </button>
          <button
            onClick={() => {
              setEvent(''); setUserEmail(''); setTool(''); setDateFrom(''); setDateTo('');
              load(0);
            }}
            className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 transition"
          >
            Réinitialiser
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 animate-pulse">Chargement...</div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-medium text-gray-600 w-8" />
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Utilisateur</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Outil</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {page?.items.map((ev) => (
                  <>
                    <tr
                      key={ev.id}
                      className="hover:bg-gray-50 transition cursor-pointer"
                      onClick={() => setExpanded(expanded === ev.id ? null : ev.id)}
                    >
                      <td className="px-4 py-3 text-gray-400">
                        <svg
                          className={`w-4 h-4 transition-transform ${expanded === ev.id ? 'rotate-90' : ''}`}
                          fill="none" viewBox="0 0 24 24" stroke="currentColor"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                        {new Date(ev.ts).toLocaleString('fr-FR')}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${EVENT_COLORS[ev.event] || 'bg-gray-100 text-gray-700'}`}>
                          {ev.event}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-700 truncate max-w-xs">{ev.user_email || '—'}</td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">{ev.tool || '—'}</td>
                      <td className="px-4 py-3 text-xs text-gray-400">{ev.ip || '—'}</td>
                    </tr>
                    {expanded === ev.id && (
                      <tr key={`${ev.id}-detail`}>
                        <td colSpan={6} className="px-8 py-4 bg-gray-50">
                          <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono overflow-x-auto">
                            {JSON.stringify(ev.details, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {page?.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      Aucun événement
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            {/* Pagination */}
            {page && page.total > PAGE_SIZE && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200">
                <span className="text-sm text-gray-500">
                  {page.total.toLocaleString('fr-FR')} événement{page.total > 1 ? 's' : ''} — page {currentPage}/{totalPages}
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={offset === 0}
                    onClick={() => load(Math.max(0, offset - PAGE_SIZE))}
                    className="px-3 py-1 text-sm border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition"
                  >
                    Précédent
                  </button>
                  <button
                    disabled={offset + PAGE_SIZE >= page.total}
                    onClick={() => load(offset + PAGE_SIZE)}
                    className="px-3 py-1 text-sm border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition"
                  >
                    Suivant
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
