import { useState } from 'react';

type Conditions = Record<string, unknown>;

interface Props {
  value: Conditions;
  onChange: (c: Conditions) => void;
}

// ── Condition type definitions ──────────────────────────────────

interface BooleanDef { kind: 'boolean'; key: string; label: string; hint: string }
interface NumberDef  { kind: 'number';  key: string; label: string; hint: string; placeholder?: string }
interface ListDef    { kind: 'list';    key: string; label: string; hint: string; placeholder?: string }

type ConditionDef = BooleanDef | NumberDef | ListDef;

const SECTIONS: { title: string; defs: ConditionDef[] }[] = [
  {
    title: 'Contrôles booléens',
    defs: [
      { kind: 'boolean', key: 'require_confirmation', label: 'Exiger confirmation humaine', hint: "Force l'utilisation de create_draft au lieu de send_email" },
      { kind: 'boolean', key: 'require_query', label: 'Requête obligatoire', hint: "Bloque si aucun terme de recherche n'est fourni" },
      { kind: 'boolean', key: 'require_filter', label: 'Filtre obligatoire', hint: "Bloque si aucun filtre n'est fourni (bases Notion)" },
      { kind: 'boolean', key: 'restrict_to_own_emails', label: 'Restreindre aux emails personnels', hint: "Masque les emails non adressés directement à l'utilisateur (To/Cc)" },
    ],
  },
  {
    title: 'Seuils numériques',
    defs: [
      { kind: 'number', key: 'max_results_cap', label: 'Limite de résultats', hint: 'Plafonne le paramètre max_results', placeholder: 'ex: 20' },
      { kind: 'number', key: 'max_date_range_days', label: 'Plage max (jours)', hint: 'Plage de dates maximum autorisée', placeholder: 'ex: 30' },
      { kind: 'number', key: 'max_attendees', label: "Nb max d'invités", hint: "Nombre maximum d'invités par événement", placeholder: 'ex: 25' },
      { kind: 'number', key: 'max_message_length', label: 'Longueur max message', hint: 'Limite en caractères (body + text + description)', placeholder: 'ex: 5000' },
    ],
  },
  {
    title: 'Listes de domaines / patterns',
    defs: [
      { kind: 'list', key: 'allowed_recipients', label: 'Destinataires autorisés', hint: 'Domaines ou adresses autorisés (To/Cc email)', placeholder: '@your-company.com' },
      { kind: 'list', key: 'allowed_attendees', label: 'Invités autorisés', hint: 'Domaines autorisés pour les invitations calendrier', placeholder: '@your-company.com' },
      { kind: 'list', key: 'blocked_recipients', label: 'Destinataires interdits', hint: 'Domaines ou adresses bloqués', placeholder: '@concurrent.com' },
      { kind: 'list', key: 'blocked_channels', label: 'Canaux interdits', hint: 'Patterns glob pour les canaux Slack bloqués', placeholder: 'hr-*, *-legal-*' },
      { kind: 'list', key: 'blocked_tools', label: 'Outils interdits', hint: "Noms d'outils à bloquer", placeholder: 'send_slack_message' },
      { kind: 'list', key: 'blocked_recipient_patterns', label: 'Destinataires auto-bloqués', hint: "Patterns anti-boucle (substring match sur le champ To)", placeholder: 'agent@, claude@, auto-reply' },
    ],
  },
];

const REGEX_PATTERN_DEFS: { key: string; label: string; hint: string }[] = [
  { key: 'blocked_patterns_body', label: 'Patterns anti-exfiltration (body/text/subject)', hint: 'Regex appliquées aux champs texte sortants — bloque credentials, clés, tokens' },
  { key: 'sensitive_senders', label: 'Expéditeurs sensibles', hint: "Regex sur l'adresse expéditeur — filtre les emails de sécurité (noreply@, security@, etc.)" },
  { key: 'sensitive_subjects', label: 'Sujets sensibles', hint: 'Regex sur le sujet — filtre password reset, OTP, 2FA, magic links, etc.' },
  { key: 'sensitive_body_patterns', label: 'Corps sensibles', hint: 'Regex sur le corps — filtre URLs auth, codes de vérification, etc.' },
  { key: 'sanitize_url_patterns', label: 'URLs à masquer', hint: 'Regex de capture — le groupe 1 est conservé, le reste remplacé par [TOKEN_MASQUE]' },
];

const KNOWN_KEYS = new Set([
  ...SECTIONS.flatMap((s) => s.defs.map((d) => d.key)),
  ...REGEX_PATTERN_DEFS.map((d) => d.key),
]);

function getExtraKeys(c: Conditions): Conditions {
  const extra: Conditions = {};
  for (const [k, v] of Object.entries(c)) {
    if (!KNOWN_KEYS.has(k)) extra[k] = v;
  }
  return extra;
}

// ── Component ───────────────────────────────────────────────────

export default function ConditionsEditor({ value, onChange }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [jsonError, setJsonError] = useState('');

  const extra = getExtraKeys(value);
  const hasExtra = Object.keys(extra).length > 0;

  function update(key: string, val: unknown) {
    const next = { ...value };
    if (val === undefined || val === null || val === '' || val === false ||
        (Array.isArray(val) && val.length === 0)) {
      delete next[key];
    } else {
      next[key] = val;
    }
    onChange(next);
  }

  function parseList(raw: string): string[] {
    return raw.split(',').map((s) => s.trim()).filter(Boolean);
  }

  function joinList(arr: unknown): string {
    return Array.isArray(arr) ? arr.join(', ') : '';
  }

  function handleRegexPatternsChange(key: string, raw: string) {
    setJsonError('');
    if (!raw.trim()) {
      update(key, undefined);
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        setJsonError('Doit être un tableau JSON de regex');
        return;
      }
      update(key, parsed);
    } catch {
      setJsonError('JSON invalide');
    }
  }

  function handleExtraJsonChange(raw: string) {
    setJsonError('');
    if (!raw.trim() || raw.trim() === '{}') return;
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        setJsonError('Doit être un objet JSON');
        return;
      }
      const next = { ...value };
      for (const k of Object.keys(extra)) delete next[k];
      Object.assign(next, parsed);
      onChange(next);
    } catch {
      setJsonError('JSON invalide');
    }
  }

  const inputCls = 'w-full px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm';
  const hintCls = 'text-xs text-gray-400 mt-0.5';

  return (
    <div className="space-y-5">
      {SECTIONS.map((section) => {
        const active = section.defs.filter((d) => value[d.key] !== undefined);
        const inactive = section.defs.filter((d) => value[d.key] === undefined);

        return (
          <fieldset key={section.title} className="space-y-3">
            <legend className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{section.title}</legend>

            {active.map((def) => (
              <ConditionField key={def.key} def={def} value={value} inputCls={inputCls} hintCls={hintCls}
                update={update} parseList={parseList} joinList={joinList} />
            ))}

            {inactive.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {inactive.map((def) => (
                  <button key={def.key} type="button"
                    onClick={() => update(def.key, def.kind === 'boolean' ? true : def.kind === 'number' ? 0 : [])}
                    className="text-xs px-2.5 py-1 rounded-full border border-dashed border-gray-300 text-gray-500 hover:border-primary-400 hover:text-primary-600 transition"
                  >
                    + {def.label}
                  </button>
                ))}
              </div>
            )}
          </fieldset>
        );
      })}

      {/* Regex pattern arrays — raw JSON editors */}
      <fieldset className="space-y-3">
        <legend className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Patterns regex (tableaux JSON)</legend>

        {REGEX_PATTERN_DEFS.map((def) => {
          const patterns = (value[def.key] as string[] | undefined) ?? [];
          const hasPatterns = patterns.length > 0;

          return hasPatterns ? (
            <div key={def.key} className="group">
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-700">{def.label}</label>
                <button type="button" onClick={() => update(def.key, undefined)}
                  className="text-xs text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-600 transition">Retirer</button>
              </div>
              <textarea
                defaultValue={JSON.stringify(patterns, null, 2)}
                onBlur={(e) => handleRegexPatternsChange(def.key, e.target.value)}
                rows={Math.min(patterns.length + 2, 10)}
                spellCheck={false}
                className={`${inputCls} font-mono`}
              />
              <p className={hintCls}>{def.hint}</p>
            </div>
          ) : null;
        })}

        {(() => {
          const inactive = REGEX_PATTERN_DEFS.filter((d) => !value[d.key] || (value[d.key] as string[]).length === 0);
          return inactive.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {inactive.map((def) => (
                <button key={def.key} type="button"
                  onClick={() => update(def.key, ['(?i)example'])}
                  className="text-xs px-2.5 py-1 rounded-full border border-dashed border-gray-300 text-gray-500 hover:border-primary-400 hover:text-primary-600 transition"
                >
                  + {def.label}
                </button>
              ))}
            </div>
          ) : null;
        })()}
      </fieldset>

      {/* Advanced JSON fallback */}
      {(hasExtra || showAdvanced) && (
        <fieldset className="space-y-2">
          <legend className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Conditions avancées (JSON)</legend>
          <textarea
            defaultValue={JSON.stringify(extra, null, 2)}
            onBlur={(e) => handleExtraJsonChange(e.target.value)}
            rows={4}
            spellCheck={false}
            className={`${inputCls} font-mono`}
          />
          <p className={hintCls}>Clés JSON supplémentaires non gérées par l'éditeur structuré</p>
        </fieldset>
      )}

      {!showAdvanced && !hasExtra && (
        <button type="button" onClick={() => setShowAdvanced(true)}
          className="text-xs text-gray-400 hover:text-gray-600 transition">
          Afficher l'éditeur JSON avancé
        </button>
      )}

      {jsonError && (
        <p className="text-xs text-red-500">{jsonError}</p>
      )}
    </div>
  );
}

// ── Individual condition field ──────────────────────────────────

function ConditionField({ def, value, inputCls, hintCls, update, parseList, joinList }: {
  def: ConditionDef;
  value: Conditions;
  inputCls: string;
  hintCls: string;
  update: (key: string, val: unknown) => void;
  parseList: (raw: string) => string[];
  joinList: (arr: unknown) => string;
}) {
  const current = value[def.key];

  return (
    <div className="flex items-start gap-3 group">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-0.5">
          <label className="text-sm font-medium text-gray-700">{def.label}</label>
          <button type="button" onClick={() => update(def.key, undefined)}
            className="text-xs text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-600 transition">
            Retirer
          </button>
        </div>

        {def.kind === 'boolean' && (
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={!!current}
              onChange={(e) => update(def.key, e.target.checked || undefined)}
              className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            <span className="text-sm text-gray-600">Activé</span>
          </label>
        )}

        {def.kind === 'number' && (
          <input type="number" min={0} value={current as number ?? ''}
            onChange={(e) => update(def.key, e.target.value ? parseInt(e.target.value, 10) : undefined)}
            placeholder={(def as NumberDef).placeholder}
            className={inputCls} />
        )}

        {def.kind === 'list' && (
          <input type="text" value={joinList(current)}
            onChange={(e) => {
              const list = parseList(e.target.value);
              update(def.key, list.length ? list : undefined);
            }}
            placeholder={(def as ListDef).placeholder}
            className={inputCls} />
        )}

        <p className={hintCls}>{def.hint}</p>
      </div>
    </div>
  );
}
