import React, { useState, useEffect } from 'react';
import { HardDrive, Download, Trash2, RefreshCw, Loader2, Folder, Disc, FileArchive, File, CheckSquare, Square, AlertTriangle } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface Artifact {
  filename: string;
  filepath: string;
  size_bytes: number;
  size_human: string;
  format: string;
  modified_at: string;
}

interface Summary {
  outputs_dir: string;
  total_files: number;
  total_bytes: number;
  total_human: string;
  free_bytes: number;
  free_human: string;
}

export default function StorageTab() {
  const { t } = useTranslation();
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);

  const fetchStorageData = async () => {
    setLoading(true);
    try {
      const [sumRes, artRes] = await Promise.all([
        fetch('/api/storage/summary'),
        fetch('/api/storage/artifacts')
      ]);
      if (sumRes.ok) {
        const sumData = await sumRes.json();
        setSummary(sumData);
      }
      if (artRes.ok) {
        const artData = await artRes.json();
        setArtifacts(artData);
      }
    } catch (err) {
      console.error('Failed to fetch storage data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStorageData();
  }, []);

  const toggleSelectAll = () => {
    if (selectedFiles.length === filteredArtifacts.length) {
      setSelectedFiles([]);
    } else {
      setSelectedFiles(filteredArtifacts.map((a) => a.filename));
    }
  };

  const toggleSelectFile = (filename: string) => {
    if (selectedFiles.includes(filename)) {
      setSelectedFiles(selectedFiles.filter((f) => f !== filename));
    } else {
      setSelectedFiles([...selectedFiles, filename]);
    }
  };

  const handleDeleteSingle = async (filename: string) => {
    try {
      const res = await fetch(`/api/storage/artifacts/${encodeURIComponent(filename)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        setDeleteTarget(null);
        setSelectedFiles((prev) => prev.filter((f) => f !== filename));
        fetchStorageData();
      }
    } catch (err) {
      console.error('Failed to delete file:', err);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedFiles.length === 0) return;
    try {
      const res = await fetch('/api/storage/artifacts/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames: selectedFiles })
      });
      if (res.ok) {
        setIsBulkDeleting(false);
        setSelectedFiles([]);
        fetchStorageData();
      }
    } catch (err) {
      console.error('Failed to bulk delete files:', err);
    }
  };

  const filteredArtifacts = artifacts.filter((a) =>
    a.filename.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-5 animate-tab-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-zinc-800 pb-4 gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
            <HardDrive size={22} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-zinc-50 tracking-tight">{t('storageTitle')}</h2>
            <p className="text-[11px] text-zinc-400 font-medium">{t('storageSubtitle')}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {selectedFiles.length > 0 && (
            <button
              onClick={() => setIsBulkDeleting(true)}
              className="px-3.5 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-xl text-xs font-bold transition-all shadow-md flex items-center gap-2 cursor-pointer"
            >
              <Trash2 size={14} />
              <span>{t('deleteSelected', { count: selectedFiles.length })}</span>
            </button>
          )}

          <button
            onClick={fetchStorageData}
            className="p-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 transition-colors cursor-pointer"
            title="Refresh Storage"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center justify-between shadow-lg">
            <div>
              <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">
                {t('totalArtifacts')}
              </span>
              <span className="text-2xl font-black font-mono text-amber-400">{summary.total_files}</span>
            </div>
            <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl text-zinc-400">
              <Folder size={20} />
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center justify-between shadow-lg">
            <div>
              <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">
                {t('totalStorageUsed')}
              </span>
              <span className="text-2xl font-black font-mono text-zinc-100">{summary.total_human}</span>
            </div>
            <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl text-amber-400">
              <HardDrive size={20} />
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center justify-between shadow-lg">
            <div>
              <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">
                {t('freeStorageAvailable')}
              </span>
              <span className="text-2xl font-black font-mono text-emerald-400">{summary.free_human}</span>
            </div>
            <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl text-emerald-400">
              <HardDrive size={20} />
            </div>
          </div>
        </div>
      )}

      {/* Search Bar & Location Directory Hint */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-900/50 p-3 px-4 border border-zinc-800/80 rounded-2xl">
        <div className="flex items-center gap-2 text-xs font-mono text-zinc-400 w-full sm:w-auto overflow-x-auto">
          <span className="text-zinc-500 font-bold uppercase text-[10px] tracking-wider">Path:</span>
          <code className="text-amber-400 bg-zinc-950 px-2.5 py-1 rounded-lg border border-zinc-800">
            {summary?.outputs_dir || '/opt/data/duro_workspace/outputs'}
          </code>
        </div>

        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by filename..."
          className="w-full sm:w-64 bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-amber-500/50"
        />
      </div>

      {/* Table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden shadow-xl">
        {loading && artifacts.length === 0 ? (
          <div className="flex items-center justify-center p-12 text-zinc-400">
            <Loader2 className="animate-spin mr-2" size={20} />
            <span>Scanning storage directory...</span>
          </div>
        ) : filteredArtifacts.length === 0 ? (
          <div className="p-12 text-center text-zinc-500 text-sm">
            {t('noArtifactsInStorage')}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-950/50 text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                  <th className="py-3 px-4 w-10 text-center">
                    <button
                      type="button"
                      onClick={toggleSelectAll}
                      className="text-zinc-400 hover:text-amber-400 transition-colors cursor-pointer"
                    >
                      {selectedFiles.length === filteredArtifacts.length && filteredArtifacts.length > 0 ? (
                        <CheckSquare size={16} className="text-amber-500" />
                      ) : (
                        <Square size={16} />
                      )}
                    </button>
                  </th>
                  <th className="py-3 px-4">Filename</th>
                  <th className="py-3 px-4">Format</th>
                  <th className="py-3 px-4">File Size</th>
                  <th className="py-3 px-4">Last Modified</th>
                  <th className="py-3 px-4 text-right">{t('actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50 text-xs">
                {filteredArtifacts.map((art) => {
                  const isSelected = selectedFiles.includes(art.filename);
                  return (
                    <tr
                      key={art.filename}
                      className={`hover:bg-zinc-800/40 transition-colors ${
                        isSelected ? 'bg-amber-500/5' : ''
                      }`}
                    >
                      <td className="py-3 px-4 text-center">
                        <button
                          type="button"
                          onClick={() => toggleSelectFile(art.filename)}
                          className="text-zinc-400 hover:text-amber-400 transition-colors cursor-pointer"
                        >
                          {isSelected ? (
                            <CheckSquare size={16} className="text-amber-500" />
                          ) : (
                            <Square size={16} />
                          )}
                        </button>
                      </td>

                      <td className="py-3 px-4 font-mono font-bold text-zinc-200">
                        <div className="flex items-center gap-2.5">
                          {art.format === 'iso' ? (
                            <Disc size={16} className="text-amber-400 flex-shrink-0" />
                          ) : art.format === 'raw_xz' ? (
                            <FileArchive size={16} className="text-emerald-400 flex-shrink-0" />
                          ) : (
                            <File size={16} className="text-cyan-400 flex-shrink-0" />
                          )}
                          <span className="truncate max-w-md">{art.filename}</span>
                        </div>
                      </td>

                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                            art.format === 'iso'
                              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                              : art.format === 'raw_xz'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                          }`}
                        >
                          {art.format.toUpperCase()}
                        </span>
                      </td>

                      <td className="py-3 px-4 font-mono text-zinc-300 font-semibold">{art.size_human}</td>

                      <td className="py-3 px-4 font-mono text-zinc-400">
                        {new Date(art.modified_at).toLocaleString()}
                      </td>

                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <a
                            href={`/api/storage/artifacts/${encodeURIComponent(art.filename)}/download`}
                            className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 rounded-lg text-xs font-bold transition-colors flex items-center gap-1"
                            title="Download artifact file"
                          >
                            <Download size={13} />
                            <span>Download</span>
                          </a>

                          <button
                            onClick={() => setDeleteTarget(art.filename)}
                            className="p-1.5 text-zinc-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
                            title="Delete file from server disk"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Delete Single Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
          <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-3xl p-6 shadow-2xl space-y-4 animate-modal-in">
            <div className="flex items-center gap-3 text-rose-400">
              <div className="p-2.5 bg-rose-500/10 rounded-2xl border border-rose-500/20">
                <AlertTriangle size={22} />
              </div>
              <h3 className="text-lg font-bold text-zinc-100">Delete Artifact File?</h3>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed">
              {t('confirmDeleteFile', { name: deleteTarget })}
            </p>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-zinc-900">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-bold text-zinc-300 transition-colors cursor-pointer"
              >
                {t('cancel')}
              </button>
              <button
                onClick={() => handleDeleteSingle(deleteTarget)}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-xs font-bold transition-colors cursor-pointer shadow-lg shadow-rose-600/20"
              >
                {t('delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Bulk Confirmation Modal */}
      {isBulkDeleting && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
          <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-3xl p-6 shadow-2xl space-y-4 animate-modal-in">
            <div className="flex items-center gap-3 text-rose-400">
              <div className="p-2.5 bg-rose-500/10 rounded-2xl border border-rose-500/20">
                <AlertTriangle size={22} />
              </div>
              <h3 className="text-lg font-bold text-zinc-100">Bulk Delete Artifacts?</h3>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed">
              {t('confirmBulkDelete', { count: selectedFiles.length })}
            </p>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-zinc-900">
              <button
                onClick={() => setIsBulkDeleting(false)}
                className="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-bold text-zinc-300 transition-colors cursor-pointer"
              >
                {t('cancel')}
              </button>
              <button
                onClick={handleBulkDelete}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-xs font-bold transition-colors cursor-pointer shadow-lg shadow-rose-600/20"
              >
                {t('delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
