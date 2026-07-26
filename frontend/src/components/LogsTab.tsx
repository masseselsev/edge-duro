import React, { useState, useEffect } from 'react';
import { Terminal, Shield, RefreshCw, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import { getSavedLimit, saveLimit } from '../utils/storage';

export default function LogsTab() {
  const { t } = useTranslation();
  const [subTab, setSubTab] = useState<'system' | 'audit'>('system');
  const [systemLogs, setSystemLogs] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState<number>(() => getSavedLimit('logs_system', 25));

  const fetchLogs = async (pageNum = page, currentLimit = limit) => {
    setLoading(true);
    try {
      if (subTab === 'system') {
        const res = await fetch(`/api/logs/system?page=${pageNum}&limit=${currentLimit}`);
        if (res.ok) {
          const data = await res.json();
          setSystemLogs(data.items || []);
          setTotal(data.total || 0);
          setPages(data.pages || 1);
        }
      } else {
        const res = await fetch(`/api/logs/audit?page=${pageNum}&limit=${currentLimit}`);
        if (res.ok) {
          const data = await res.json();
          setAuditLogs(data.items || []);
          setTotal(data.total || 0);
          setPages(data.pages || 1);
        }
      }
    } catch (err) {
      console.error('Failed to fetch logs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const savedLimit = getSavedLimit(`logs_${subTab}`, 25);
    setLimit(savedLimit);
    setPage(1);
    fetchLogs(1, savedLimit);
  }, [subTab]);

  useEffect(() => {
    fetchLogs(page, limit);
  }, [page, limit]);

  return (
    <div className="space-y-6 animate-tab-in">
      {/* Header matching edge-bro & edge-zero */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-zinc-50">{t('tabLogs')}</h2>
          <p className="text-sm text-zinc-400">System application events & administrative audit trails</p>
        </div>

        <div className="flex items-center gap-3 self-stretch sm:self-auto justify-end">
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
            onClick={() => fetchLogs()}
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

        {/* Pagination Bar */}
        <div className="px-6 py-3 border-t border-zinc-800/80 bg-zinc-950/40 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-zinc-400">
          <div className="flex items-center gap-4">
            <span>
              {t('showingEntries')
                .replace('{start}', String(total > 0 ? (page - 1) * limit + 1 : 0))
                .replace('{end}', String(Math.min(page * limit, total)))
                .replace('{total}', String(total))}
            </span>

            <div className="flex items-center gap-1.5">
              <select
                value={limit}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                  const val = Number(e.target.value);
                  setLimit(val);
                  setPage(1);
                  saveLimit(`logs_${subTab}`, val);
                }}
                className="bg-zinc-900 border border-zinc-800 rounded-lg px-2 py-1 text-xs font-mono text-zinc-300 focus:outline-none focus:border-zinc-700 cursor-pointer"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
              <span>{t('perPage')}</span>
            </div>
          </div>

          {pages > 1 && (
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p: number) => Math.max(p - 1, 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-300 transition-colors cursor-pointer"
              >
                <ChevronLeft size={14} />
                <span>{t('previous')}</span>
              </button>
              <span className="px-2 font-mono font-medium text-zinc-300">
                {t('pageOf').replace('{page}', String(page)).replace('{pages}', String(pages))}
              </span>
              <button
                disabled={page >= pages}
                onClick={() => setPage((p: number) => Math.min(p + 1, pages))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-300 transition-colors cursor-pointer"
              >
                <span>{t('next')}</span>
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
