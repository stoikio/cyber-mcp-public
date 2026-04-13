import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface EventCount {
  event: string;
  count: number;
}
interface DailyCount {
  date: string;
  count: number;
}
interface TopUser {
  email: string;
  count: number;
}
interface AuditEvent {
  id: number;
  ts: string;
  event: string;
  user_email: string;
  tool: string;
  details: Record<string, unknown>;
}
interface Stats {
  total_events: number;
  total_blocked: number;
  total_rate_limited: number;
  active_users: number;
  active_policies: number;
  active_api_keys: number;
  events_by_type: EventCount[];
  events_by_day: DailyCount[];
  top_users: TopUser[];
  recent_events: AuditEvent[];
}

const EVENT_COLORS: Record<string, string> = {
  TOOL_CALL: 'bg-blue-100 text-blue-700',
  TOOL_OK: 'bg-green-100 text-green-700',
  BLOCKED: 'bg-red-100 text-red-700',
  POLICY_BLOCKED: 'bg-red-100 text-red-700',
  RATE_LIMITED: 'bg-amber-100 text-amber-700',
  EMAIL_SENT: 'bg-emerald-100 text-emerald-700',
  SLACK_SENT: 'bg-purple-100 text-purple-700',
  SLACK_CHANNEL_READ: 'bg-violet-100 text-violet-700',
  AUTH_FAILED: 'bg-rose-100 text-rose-700',
};

function eventBadge(event: string) {
  const cls = EVENT_COLORS[event] || 'bg-gray-100 text-gray-700';
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {event}
    </span>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get<Stats>('/stats').then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return <div className="text-red-600 bg-red-50 rounded-lg p-4">{error}</div>;
  }
  if (!stats) {
    return <div className="text-gray-400 animate-pulse">Chargement...</div>;
  }

  const cards = [
    { label: 'Total événements', value: stats.total_events, color: 'text-primary-600' },
    { label: 'Bloqués', value: stats.total_blocked, color: 'text-red-600' },
    { label: 'Rate limited', value: stats.total_rate_limited, color: 'text-amber-600' },
    { label: 'Utilisateurs actifs (7j)', value: stats.active_users, color: 'text-emerald-600' },
    { label: 'Politiques actives', value: stats.active_policies, color: 'text-indigo-600' },
    { label: 'Clés API actives', value: stats.active_api_keys, color: 'text-violet-600' },
  ];

  const maxDay = Math.max(...stats.events_by_day.map((d) => d.count), 1);

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">Tableau de bord</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {cards.map(({ label, value, color }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="text-xs text-gray-500 mb-1">{label}</div>
            <div className={`text-2xl font-bold ${color}`}>{value.toLocaleString('fr-FR')}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Events by day chart */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Événements (7 derniers jours)</h2>
          <div className="flex items-end gap-2 h-40">
            {stats.events_by_day.map((d) => (
              <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
                <span className="text-xs text-gray-500">{d.count}</span>
                <div
                  className="w-full bg-primary-500 rounded-t"
                  style={{ height: `${(d.count / maxDay) * 100}%`, minHeight: 4 }}
                />
                <span className="text-[10px] text-gray-400">
                  {new Date(d.date).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })}
                </span>
              </div>
            ))}
            {stats.events_by_day.length === 0 && (
              <div className="text-gray-400 text-sm w-full text-center">Aucune donnée</div>
            )}
          </div>
        </div>

        {/* Events by type */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Événements par type</h2>
          <div className="space-y-2">
            {stats.events_by_type.slice(0, 8).map(({ event, count }) => {
              const maxType = stats.events_by_type[0]?.count || 1;
              return (
                <div key={event} className="flex items-center gap-3">
                  <span className="text-xs text-gray-600 w-36 truncate font-mono">{event}</span>
                  <div className="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary-500 rounded-full"
                      style={{ width: `${(count / maxType) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500 w-12 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Top users */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Top utilisateurs (7j)</h2>
          <div className="space-y-2">
            {stats.top_users.map(({ email, count }, i) => (
              <div key={email} className="flex items-center gap-3">
                <span className="w-5 text-xs text-gray-400 text-right">{i + 1}</span>
                <span className="flex-1 text-sm text-gray-700 truncate">{email}</span>
                <span className="text-sm font-medium text-gray-900">{count}</span>
              </div>
            ))}
            {stats.top_users.length === 0 && (
              <div className="text-gray-400 text-sm">Aucun utilisateur</div>
            )}
          </div>
        </div>

        {/* Recent events */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Activité récente</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {stats.recent_events.slice(0, 12).map((ev) => (
              <div key={ev.id} className="flex items-center gap-3 text-sm">
                <span className="text-xs text-gray-400 w-14 shrink-0">
                  {new Date(ev.ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                </span>
                {eventBadge(ev.event)}
                <span className="text-gray-600 truncate">{ev.user_email || '—'}</span>
                {ev.tool && <span className="text-gray-400 font-mono text-xs">{ev.tool}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
