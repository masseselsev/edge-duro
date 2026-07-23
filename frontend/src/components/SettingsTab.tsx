import React, { useState, useEffect } from 'react';
import { Settings as Gear, Loader2, Save } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import { SearchableSelect } from './SearchableSelect';

interface SettingsTabProps {
  onSettingsUpdated: (settings: any) => void;
}

const TIMEZONES = [
  { label: 'Browser Local', value: 'Browser Local' },
  { label: 'UTC', value: 'UTC' },
  { label: 'Europe/Moscow', value: 'Europe/Moscow' },
  { label: 'Europe/Kyiv', value: 'Europe/Kyiv' },
  { label: 'Europe/London', value: 'Europe/London' },
  { label: 'America/New_York', value: 'America/New_York' },
];

export default function SettingsTab({ onSettingsUpdated }: SettingsTabProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [serverName, setServerName] = useState('Edge-D.U.R.O.');
  const [timezone, setTimezone] = useState('Browser Local');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    fetch('/api/settings')
      .then((res) => res.json())
      .then((data) => {
        if (data) {
          setServerName(data.server_name || 'Edge-D.U.R.O.');
          setTimezone(data.timezone || 'Browser Local');
        }
      })
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMsg('');

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_name: serverName,
          timezone,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save settings');
      }

      onSettingsUpdated(data);
      setMsg('Settings saved successfully!');
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-zinc-400">
        <Loader2 className="animate-spin mr-2" size={20} />
        <span>Loading settings...</span>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6 animate-tab-in">
      <div className="flex items-center gap-3 border-b border-zinc-800 pb-4">
        <div className="p-2.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
          <Gear size={22} />
        </div>
        <div>
          <h2 className="text-lg font-bold text-zinc-50">{t('tabSettings')}</h2>
          <p className="text-xs text-zinc-400">Global Edge D.U.R.O. factory configuration</p>
        </div>
      </div>

      {msg && (
        <div className={`p-3.5 rounded-xl text-xs font-semibold ${msg.startsWith('Error') ? 'bg-rose-500/10 border border-rose-500/20 text-rose-400' : 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'}`}>
          {msg}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6 bg-zinc-900 border border-zinc-800 rounded-2xl p-6 shadow-xl">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider pl-1">{t('serverName')}</label>
            <input
              type="text"
              value={serverName}
              onChange={(e) => setServerName(e.target.value)}
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-lg text-zinc-100 text-sm focus:outline-none"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider pl-1">{t('timezone')}</label>
            <SearchableSelect
              options={TIMEZONES}
              value={timezone}
              onChange={setTimezone}
            />
          </div>
        </div>

        <div className="flex justify-end pt-4 border-t border-zinc-800">
          <button
            type="submit"
            disabled={saving}
            className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold text-xs rounded-xl shadow-lg transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            <span>{t('saveChanges')}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
