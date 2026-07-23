import React, { useState, useEffect } from 'react';
import { Terminal, Shield, RefreshCw, Loader2 } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

export default function LogsTab() {
  const { t } = useTranslation();
  const [subTab, setSubTab] = useState<'system' | 'audit'>('system');
  const [systemLogs, setSystemLogs] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      if (subTab === 'system') {
        const res = await fetch('/api/logs/system');
        if (res.ok) setSystemLogs(await res.json());
      } else {
        const res = await fetch('/api/logs/audit');
        if (res.ok) setAuditLogs(await res.json());
      }
    } catch (err) {
      console.error('Failed to fetch logs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [subTab]);

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-5 animate-tab-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
            <Terminal size={20} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-zinc-50 tracking-tight">{t('tabLogs')}</h2>
            <p className="text-[11px] text-zinc-400 font-medium">System application events & administrative audit trails</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex bg-zinc-950 p-1 rounded-xl border border-zinc-800">
            <button
              onClick={() => setSubTab('system')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                subTab === 'system' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Terminal size={14} />
              <span>{t('systemLogs')}</span>
            </button>
            <button
              onClick={() => setSubTab('audit')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                subTab === 'audit' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Shield size={14} />
              <span>{t('auditLogs')}</span>
            </button>
          </div>

          <button
            onClick={fetchLogs}
            className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 transition-colors cursor-pointer"
            title="Refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="flex items-center justify-center p-12 text-zinc-400">
            <Loader2 className="animate-spin mr-2" size={20} />
            <span>Loading log entries...</span>
          </div>
        ) : subTab === 'system' ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-950/50 text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                  <th className="py-3 px-4">Time</th>
                  <th className="py-3 px-4">Level</th>
                  <th className="py-3 px-4">Message</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50 text-xs font-mono">
                {systemLogs.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-8 text-center text-zinc-500 font-sans">No log entries found.</td>
                  </tr>
                ) : (
                  systemLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="py-2.5 px-4 text-zinc-400 whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
                      <td className="py-2.5 px-4">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          log.level === 'ERROR' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                          log.level === 'WARNING' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                          'bg-zinc-800 text-zinc-300'
                        }`}>
                          {log.level}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-zinc-200">{log.message}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-950/50 text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                  <th className="py-3 px-4">Time</th>
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Details</th>
                  <th className="py-3 px-4">IP Address</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50 text-xs font-mono">
                {auditLogs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-zinc-500 font-sans">No audit entries found.</td>
                  </tr>
                ) : (
                  auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="py-2.5 px-4 text-zinc-400 whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
                      <td className="py-2.5 px-4 text-amber-400 font-bold">{log.username}</td>
                      <td className="py-2.5 px-4"><span className="bg-zinc-800 text-zinc-200 px-2 py-0.5 rounded text-[10px]">{log.action}</span></td>
                      <td className="py-2.5 px-4 text-zinc-300 font-sans">{log.details || '—'}</td>
                      <td className="py-2.5 px-4 text-zinc-400">{log.ip_address || '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
