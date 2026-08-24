import React, { useState, useEffect } from 'react';
import { History, Terminal, Download, XCircle, RefreshCw, Loader2, FileText, ChevronLeft, ChevronRight, Cpu } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import BuildLogStream from './BuildLogStream';
import RecipeViewerModal from './RecipeViewerModal';
import MissingPackagesModal from './MissingPackagesModal';
import { BOARDS } from './BoardSelector';
import { getSavedLimit, saveLimit } from '../utils/storage';

export default function BuildsTab() {
  const { t } = useTranslation();
  const [builds, setBuilds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeLogBuild, setActiveLogBuild] = useState<any | null>(null);
  const [selectedRecipe, setSelectedRecipe] = useState<any | null>(null);
  const [missingPkgBuild, setMissingPkgBuild] = useState<any | null>(null);

  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState<number>(() => getSavedLimit('builds', 25));

  const fetchBuilds = async (isInitial = false, pageNum = page, currentLimit = limit) => {
    if (isInitial) setLoading(true);
    try {
      const res = await fetch(`/api/builds?page=${pageNum}&limit=${currentLimit}`);
      if (res.ok) {
        const data = await res.json();
        setBuilds(data.items || []);
        setTotal(data.total || 0);
        setPages(data.pages || 1);
      }
    } catch (err) {
      console.error('Failed to fetch builds:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuilds(true, page, limit);
    const interval = setInterval(() => fetchBuilds(false, page, limit), 8000);
    return () => clearInterval(interval);
  }, [page, limit]);

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
    <div className="space-y-6 animate-tab-in">
      {/* Header matching edge-bro & edge-zero */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-zinc-50">{t('buildHistoryTitle')}</h2>
          <p className="text-sm text-zinc-400">View image compilation task runs, logs, and artifacts</p>
        </div>

        <button
          onClick={() => fetchBuilds(true)}
          className="p-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 transition-colors cursor-pointer"
          title="Refresh"
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="bg-zinc-900/50 border border-zinc-800/80 rounded-2xl overflow-hidden shadow-xl">
        {loading && builds.length === 0 ? (
          <div className="flex items-center justify-center p-12 text-zinc-400">
            <Loader2 className="animate-spin mr-2" size={20} />
            <span>{t('loadingBuildHistory')}</span>
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
                  <th className="px-6 py-3.5">{t('buildId')}</th>
                  <th className="px-6 py-3.5">{t('status')}</th>
                  <th className="px-6 py-3.5">{t('startedAt')}</th>
                  <th className="px-6 py-3.5">{t('duration')}</th>
                  <th className="px-6 py-3.5">{t('triggeredBy')}</th>
                  <th className="px-6 py-3.5 text-right">{t('actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50 text-xs">
                {builds.map((build) => (
                  <tr key={build.id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="px-6 py-3.5 font-mono text-zinc-300 font-bold">
                      <div className="flex items-center gap-2">
                        <span>{build.id.slice(0, 8)}...</span>
                        {build.recipe?.distribution === 'armbian' && (
                          <span
                            title={BOARDS.find((b) => b.id === build.recipe.board)?.name || build.recipe.board}
                            className="shrink-0 flex items-center justify-center w-5 h-5 rounded-full bg-zinc-800/60 text-zinc-400 border border-zinc-700"
                          >
                            <Cpu size={10} />
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-3.5">
                      <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold ${
                        build.status === 'SUCCESS' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        build.status === 'RUNNING' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse' :
                        build.status === 'PENDING' ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' :
                        build.status === 'CANCELLED' ? 'bg-zinc-800 text-zinc-400' :
                        'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      }`}>
                        {build.status}
                      </span>
                      {build.missing_packages?.length > 0 && (
                        <button
                          onClick={() => setMissingPkgBuild(build)}
                          className={`ml-2 px-2 py-1 rounded-full text-[10px] font-bold border cursor-pointer transition-colors ${
                            build.status === 'FAILED'
                              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/20'
                              : 'bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20'
                          }`}
                        >
                          {(build.status === 'FAILED' ? t('missingPkgsUnavailable') : t('missingPkgsSkipped'))
                            .replace('{n}', String(build.missing_packages.length))}
                        </button>
                      )}
                    </td>
                    <td className="px-6 py-3.5 text-zinc-400 font-mono">{new Date(build.created_at).toLocaleString()}</td>
                    <td className="px-6 py-3.5 text-zinc-400 font-mono">{build.duration_seconds ? `${build.duration_seconds}s` : '—'}</td>
                    <td className="px-6 py-3.5 text-zinc-300">{build.triggered_by || 'system'}</td>
                    <td className="px-6 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {build.recipe && (
                          <button
                            onClick={() => setSelectedRecipe(build.recipe)}
                            className="px-2.5 py-1 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/20 rounded-lg text-xs font-bold transition-colors flex items-center gap-1 cursor-pointer"
                            title={t('viewRecipe')}
                          >
                            <FileText size={13} />
                            <span>{t('viewRecipe')}</span>
                          </button>
                        )}
                        <button
                          onClick={() => setActiveLogBuild(build)}
                          className="px-2.5 py-1 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 rounded-lg text-xs font-bold transition-colors flex items-center gap-1 cursor-pointer"
                        >
                          <Terminal size={13} />
                          <span>{t('viewLogs')}</span>
                        </button>
                        {build.artifact_path && (
                          <a
                            href={`/api/builds/${build.id}/download?format=raw_xz`}
                            className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 rounded-lg text-xs font-bold transition-colors flex items-center gap-1"
                            title="Download compressed RAW.XZ image"
                          >
                            <Download size={13} />
                            <span>RAW.XZ</span>
                          </a>
                        )}
                        {build.iso_artifact_path && (
                          <a
                            href={`/api/builds/${build.id}/download?format=iso`}
                            className="px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 text-amber-400 border border-zinc-800 rounded-lg text-xs font-bold transition-colors flex items-center gap-1"
                            title="Download bootable ISO image"
                          >
                            <Download size={13} />
                            <span>ISO</span>
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
                  saveLimit('builds', val);
                }}
                className="bg-zinc-900 border border-zinc-800 rounded-lg px-2 py-1 text-xs font-mono text-zinc-300 focus:outline-hidden focus:border-zinc-700 cursor-pointer"
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

      {activeLogBuild && (
        <BuildLogStream
          buildId={activeLogBuild.id}
          recipeName={`Recipe #${activeLogBuild.recipe_id}`}
          onClose={() => setActiveLogBuild(null)}
        />
      )}

      {selectedRecipe && (
        <RecipeViewerModal recipe={selectedRecipe} onClose={() => setSelectedRecipe(null)} />
      )}

      {missingPkgBuild && (
        <MissingPackagesModal build={missingPkgBuild} onClose={() => setMissingPkgBuild(null)} />
      )}
    </div>
  );
}
