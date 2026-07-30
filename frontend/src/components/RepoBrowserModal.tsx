import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Boxes, X, Search, Loader2, Check, AlertTriangle, RefreshCw, Package } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

export interface RepoPackage {
  name: string;
  version: string;
  section: string;
  architecture: string;
  summary: string;
  description: string;
  depends: string;
  installed_size_kb: number;
}

interface RepoRef {
  name?: string;
  url?: string;
  suite?: string;
  components?: string;
}

interface RepoBrowserModalProps {
  recipeId?: number;
  repositories: RepoRef[];
  selected: string[];
  onClose: () => void;
  onApply: (packages: string[]) => void;
}

const PAGE_SIZE = 200;

const formatSize = (kb: number) => {
  if (!kb) return '';
  if (kb < 1024) return `${kb} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
};

export default function RepoBrowserModal({
  recipeId,
  repositories,
  selected,
  onClose,
  onApply,
}: RepoBrowserModalProps) {
  const { t } = useTranslation();

  const [repoIndex, setRepoIndex] = useState(0);
  const [query, setQuery] = useState('');
  const [section, setSection] = useState('');
  const [loading, setLoading] = useState(false);
  const [reachable, setReachable] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [packages, setPackages] = useState<RepoPackage[]>([]);
  const [sections, setSections] = useState<{ name: string; count: number }[]>([]);
  const [total, setTotal] = useState(0);
  const [available, setAvailable] = useState(0);
  const [picked, setPicked] = useState<string[]>(selected);
  const [expanded, setExpanded] = useState<string | null>(null);

  // Debounce search so each keystroke does not fire a request.
  const debounceRef = useRef<number | undefined>(undefined);

  const load = useCallback(
    async (opts?: { refresh?: boolean }) => {
      if (!recipeId) return;
      setLoading(true);
      setErrorMsg('');
      try {
        const params = new URLSearchParams({
          repo: String(repoIndex),
          q: query,
          section,
          limit: String(PAGE_SIZE),
        });
        if (opts?.refresh) params.set('refresh', 'true');

        const res = await fetch(`/api/recipes/${recipeId}/repositories/browse?${params}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to browse repository');

        setReachable(data.reachable !== false);
        setPackages(data.packages || []);
        setSections(data.sections || []);
        setTotal(data.total || 0);
        setAvailable(data.available || 0);
        if (data.reachable === false) setErrorMsg(data.error || 'Repository unreachable');
      } catch (err: any) {
        setReachable(false);
        setErrorMsg(err.message || 'Failed to browse repository');
        setPackages([]);
        setSections([]);
      } finally {
        setLoading(false);
      }
    },
    [recipeId, repoIndex, query, section]
  );

  useEffect(() => {
    window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => load(), 250);
    return () => window.clearTimeout(debounceRef.current);
  }, [load]);

  const togglePackage = (name: string) => {
    setPicked((prev) => (prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name]));
  };

  const addedCount = useMemo(
    () => picked.filter((p) => !selected.includes(p)).length,
    [picked, selected]
  );
  const removedCount = useMemo(
    () => selected.filter((p) => !picked.includes(p)).length,
    [picked, selected]
  );

  const currentRepoLabel = (r: RepoRef) => r.name || r.url || 'repository';

  return createPortal(
    <div className="fixed inset-0 z-[10000] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-5xl h-[85vh] bg-zinc-900 border border-zinc-800 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-modal-in">

        {/* Header */}
        <div className="p-5 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/50">
          <div className="flex items-center gap-3">
            <Boxes className="w-5 h-5 text-cyan-400" />
            <div>
              <h2 className="text-sm font-bold text-zinc-100">
                {t('browseRepository') || 'Browse Repository'}
              </h2>
              <p className="text-[11px] text-zinc-500">
                {available > 0
                  ? `${available} ${t('packagesAvailable') || 'packages available'}`
                  : t('browseRepositoryHint') || 'Select packages directly from your APT repositories'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Repo tabs */}
        <div className="px-5 pt-4 flex flex-wrap gap-2">
          {repositories.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => { setRepoIndex(i); setSection(''); setExpanded(null); }}
              className={`px-3 py-1.5 rounded-lg text-[11px] font-medium border transition-colors cursor-pointer ${
                i === repoIndex
                  ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
                  : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-700'
              }`}
            >
              {currentRepoLabel(r)}
              {r.suite ? <span className="opacity-60"> · {r.suite}</span> : null}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="px-5 py-3 flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('searchPackages') || 'Search packages by name or description...'}
              className="w-full pl-9 pr-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-cyan-500 rounded-xl text-zinc-100 text-xs font-mono focus:outline-none"
            />
          </div>
          <button
            type="button"
            onClick={() => load({ refresh: true })}
            title={t('refreshIndex') || 'Refresh repository index'}
            className="p-2 text-zinc-400 hover:text-cyan-300 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Body: sections + list */}
        <div className="flex-1 min-h-0 flex gap-4 px-5 pb-3">
          {/* Sections */}
          <div className="w-44 shrink-0 overflow-y-auto space-y-1 pr-1">
            <button
              type="button"
              onClick={() => setSection('')}
              className={`w-full text-left px-2.5 py-1.5 rounded-lg text-[11px] transition-colors cursor-pointer ${
                section === '' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/50'
              }`}
            >
              {t('allSections') || 'All sections'}
            </button>
            {sections.map((s) => (
              <button
                key={s.name}
                type="button"
                onClick={() => setSection(s.name)}
                className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-[11px] transition-colors cursor-pointer ${
                  section === s.name ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/50'
                }`}
              >
                <span className="truncate font-mono">{s.name}</span>
                <span className="text-zinc-600">{s.count}</span>
              </button>
            ))}
          </div>

          {/* Package list */}
          <div className="flex-1 min-w-0 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950/50">
            {!reachable && (
              <div className="p-6 flex items-start gap-3 text-amber-400">
                <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-semibold">{t('repoUnreachable') || 'Repository unreachable'}</p>
                  <p className="text-zinc-400 mt-1">{errorMsg}</p>
                  <p className="text-zinc-500 mt-2">
                    {t('repoUnreachableHint') ||
                      'The index is fetched by the backend container, so the repository must be reachable from the server.'}
                  </p>
                </div>
              </div>
            )}

            {reachable && loading && packages.length === 0 && (
              <div className="p-8 flex items-center justify-center text-zinc-500 gap-2 text-xs">
                <Loader2 className="w-4 h-4 animate-spin" />
                {t('loading') || 'Loading...'}
              </div>
            )}

            {reachable && !loading && packages.length === 0 && (
              <div className="p-8 text-center text-zinc-500 text-xs">
                {t('noPackagesFound') || 'No packages match your search.'}
              </div>
            )}

            {packages.map((p) => {
              const isPicked = picked.includes(p.name);
              const isOpen = expanded === p.name;
              return (
                <div key={p.name} className="border-b border-zinc-800/60 last:border-0">
                  <div
                    className={`flex items-start gap-3 px-3 py-2 hover:bg-zinc-900/60 transition-colors ${
                      isPicked ? 'bg-cyan-500/[0.06]' : ''
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isPicked}
                      onChange={() => togglePackage(p.name)}
                      className="mt-0.5 w-4 h-4 rounded border-zinc-800 bg-zinc-950 text-cyan-500 focus:ring-cyan-500/20 cursor-pointer"
                    />
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : p.name)}
                      className="flex-1 min-w-0 text-left cursor-pointer"
                    >
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <span className={`font-mono text-xs ${isPicked ? 'text-cyan-300' : 'text-zinc-200'}`}>
                          {p.name}
                        </span>
                        <span className="text-[10px] text-zinc-500 font-mono">{p.version}</span>
                        {p.installed_size_kb > 0 && (
                          <span className="text-[10px] text-zinc-600">{formatSize(p.installed_size_kb)}</span>
                        )}
                      </div>
                      {p.summary && (
                        <p className="text-[11px] text-zinc-500 truncate mt-0.5">{p.summary}</p>
                      )}
                      {isOpen && (
                        <div className="mt-2 space-y-1.5 text-[11px]">
                          {p.description && p.description !== p.summary && (
                            <p className="text-zinc-400 whitespace-pre-wrap">{p.description}</p>
                          )}
                          {p.depends && (
                            <p className="text-zinc-500">
                              <span className="text-zinc-600 uppercase tracking-wider">
                                {t('dependsOn') || 'Depends'}:
                              </span>{' '}
                              <span className="font-mono">{p.depends}</span>
                            </p>
                          )}
                        </div>
                      )}
                    </button>
                  </div>
                </div>
              );
            })}

            {total > packages.length && (
              <div className="px-3 py-2 text-[11px] text-zinc-500 text-center">
                {(t('showingOf') || 'Showing {n} of {total} matches — refine your search')
                  .replace('{n}', String(packages.length))
                  .replace('{total}', String(total))}
              </div>
            )}
          </div>
        </div>

        {/* Selected chips */}
        <div className="px-5 py-3 border-t border-zinc-800 bg-zinc-950/40 max-h-28 overflow-y-auto">
          <div className="flex flex-wrap gap-1.5">
            {picked.length === 0 && (
              <span className="text-[11px] text-zinc-600">{t('noPackagesSelected') || 'No packages selected'}</span>
            )}
            {picked.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => togglePackage(name)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-[11px] font-mono hover:bg-cyan-500/20 transition-colors cursor-pointer"
              >
                <Package className="w-3 h-3" />
                {name}
                <X className="w-3 h-3 opacity-60" />
              </button>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-zinc-800 flex items-center justify-between bg-zinc-950/60">
          <span className="text-[11px] text-zinc-500">
            {picked.length} {t('selected') || 'selected'}
            {(addedCount > 0 || removedCount > 0) && (
              <span className="ml-2">
                {addedCount > 0 && <span className="text-emerald-400">+{addedCount}</span>}
                {removedCount > 0 && <span className="text-red-400 ml-1">−{removedCount}</span>}
              </span>
            )}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
            >
              {t('cancel') || 'Cancel'}
            </button>
            <button
              type="button"
              onClick={() => { onApply(picked); onClose(); }}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium text-cyan-300 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/40 rounded-lg transition-colors cursor-pointer"
            >
              <Check className="w-3.5 h-3.5" />
              {t('applySelection') || 'Apply Selection'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
