import React, { useState, useEffect } from 'react';
import { History, Terminal, Download, XCircle, RefreshCw, Loader2 } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import BuildLogStream from './BuildLogStream';

export default function BuildsTab() {
  const { t } = useTranslation();
  const [builds, setBuilds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeLogBuild, setActiveLogBuild] = useState<any | null>(null);

  const fetchBuilds = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/builds?limit=50');
      if (res.ok) {
        const data = await res.json();
        setBuilds(data.items || []);
      }
    } catch (err) {
      console.error('Failed to fetch builds:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuilds();
    const interval = setInterval(fetchBuilds, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleCancel = async (buildId: string) => {
    try {
      const res = await fetch(`/api/builds/${buildId}/cancel`, { method: 'POST' });
      if (res.ok) {
        fetchBuilds();
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6 animate-tab-in">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
            <History size={22} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-zinc-50">{t('buildHistoryTitle')}</h2>
            <p className="text-xs text-zinc-400">View image compilation task runs, logs, and artifacts</p>
          </div>
        </div>

        <button
          onClick={fetchBuilds}
          className="p-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 transition-colors cursor-pointer"
          title="Refresh"
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden shadow-xl">
        {loading && builds.length === 0 ? (
          <div className="flex items-center justify-center p-12 text-zinc-400">
            <Loader2 className="animate-spin mr-2" size={20} />
            <span>Loading build history...</span>
          </div>
        ) : builds.length === 0 ? (
          <div className="p-12 text-center text-zinc-500 text-sm">
            {t('noBuilds')}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-950/50 text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                  <th className="py-3 px-4">{t('buildId')}</th>
                  <th className="py-3 px-4">{t('status')}</th>
                  <th className="py-3 px-4">{t('startedAt')}</th>
                  <th className="py-3 px-4">{t('duration')}</th>
                  <th className="py-3 px-4">{t('triggeredBy')}</th>
                  <th className="py-3 px-4 text-right">{t('actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50 text-xs">
                {builds.map((build) => (
                  <tr key={build.id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="py-3 px-4 font-mono text-zinc-300 font-bold">{build.id.slice(0, 8)}...</td>
                    <td className="py-3 px-4">
                      <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold ${
                        build.status === 'SUCCESS' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        build.status === 'RUNNING' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse' :
                        build.status === 'PENDING' ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' :
                        build.status === 'CANCELLED' ? 'bg-zinc-800 text-zinc-400' :
                        'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      }`}>
                        {build.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400 font-mono">{new Date(build.created_at).toLocaleString()}</td>
                    <td className="py-3 px-4 text-zinc-400 font-mono">{build.duration_seconds ? `${build.duration_seconds}s` : '—'}</td>
                    <td className="py-3 px-4 text-zinc-300">{build.triggered_by || 'system'}</td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setActiveLogBuild(build)}
                          className="px-2.5 py-1 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 rounded-lg text-xs font-bold transition-colors flex items-center gap-1 cursor-pointer"
                        >
                          <Terminal size={13} />
                          <span>{t('viewLogs')}</span>
                        </button>
                        {build.artifact_path && (
                          <a
                            href={`/api/builds/${build.id}/download`}
                            className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 rounded-lg text-xs font-bold transition-colors flex items-center gap-1"
                          >
                            <Download size={13} />
                            <span>{t('downloadArtifact')}</span>
                          </a>
                        )}
                        {(build.status === 'RUNNING' || build.status === 'PENDING') && (
                          <button
                            onClick={() => handleCancel(build.id)}
                            className="p-1 text-zinc-500 hover:text-rose-400 transition-colors cursor-pointer"
                            title="Cancel Build"
                          >
                            <XCircle size={16} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {activeLogBuild && (
        <BuildLogStream
          buildId={activeLogBuild.id}
          recipeName={`Recipe #${activeLogBuild.recipe_id}`}
          onClose={() => setActiveLogBuild(null)}
        />
      )}
    </div>
  );
}
