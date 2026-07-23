import React from 'react';
import { Plus, Trash2, Key } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

export interface AptRepo {
  name: string;
  url: string;
  suite: string;
  components: string;
  gpg_key_filename?: string;
}

interface AptRepoManagerProps {
  repositories: AptRepo[];
  onChange: (repos: AptRepo[]) => void;
}

export default function AptRepoManager({ repositories, onChange }: AptRepoManagerProps) {
  const { t } = useTranslation();

  const handleAdd = () => {
    onChange([
      ...repositories,
      { name: `mirror_${repositories.length + 1}`, url: '', suite: '', components: 'main' }
    ]);
  };

  const handleUpdate = (index: number, field: keyof AptRepo, value: string) => {
    const updated = [...repositories];
    updated[index] = { ...updated[index], [field]: value };
    onChange(updated);
  };

  const handleRemove = (index: number) => {
    onChange(repositories.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
          {t('repositories')}
        </label>
        <button
          type="button"
          onClick={handleAdd}
          className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 font-bold text-xs rounded-lg transition-colors flex items-center gap-1 cursor-pointer"
        >
          <Plus size={14} />
          <span>{t('addRepository')}</span>
        </button>
      </div>

      {repositories.length === 0 ? (
        <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl text-xs text-zinc-500 text-center italic">
          No custom APT mirrors configured. Standard upstream Debian/Ubuntu repositories will be used.
        </div>
      ) : (
        <div className="space-y-3">
          {repositories.map((repo, idx) => (
            <div key={idx} className="p-3.5 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                <input
                  type="text"
                  placeholder={t('repoName')}
                  value={repo.name}
                  onChange={(e) => handleUpdate(idx, 'name', e.target.value)}
                  className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-100 font-mono"
                />
                <input
                  type="text"
                  placeholder={t('repoUrl')}
                  value={repo.url}
                  onChange={(e) => handleUpdate(idx, 'url', e.target.value)}
                  className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-100 font-mono sm:col-span-2"
                />
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder={t('repoSuite')}
                    value={repo.suite}
                    onChange={(e) => handleUpdate(idx, 'suite', e.target.value)}
                    className="w-full px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-100 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemove(idx)}
                    className="p-1.5 text-zinc-500 hover:text-rose-400 cursor-pointer shrink-0"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
