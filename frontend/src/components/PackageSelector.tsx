import React, { useState } from 'react';
import { X, Plus, Package } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface PackageSelectorProps {
  packages: string[];
  onChange: (packages: string[]) => void;
}

const COMMON_SUGGESTIONS = [
  'curl', 'wget', 'vim', 'git', 'nginx', 'wireguard-tools', 'openssh-server',
  'systemd-container', 'docker.io', 'htop', 'python3', 'python3-pip', 'rsync'
];

export default function PackageSelector({ packages, onChange }: PackageSelectorProps) {
  const { t } = useTranslation();
  const [inputVal, setInputVal] = useState('');

  const handleAdd = (pkgName: string) => {
    const cleaned = pkgName.trim().toLowerCase();
    if (cleaned && !packages.includes(cleaned)) {
      onChange([...packages, cleaned]);
      setInputVal('');
    }
  };

  const handleRemove = (pkgName: string) => {
    onChange(packages.filter((p) => p !== pkgName));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      handleAdd(inputVal);
    }
  };

  return (
    <div className="space-y-3">
      <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
        {t('packages')}
      </label>

      {/* Input box */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-500">
            <Package size={15} />
          </span>
          <input
            type="text"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('packagePlaceholder')}
            className="w-full pl-9 pr-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-lg text-zinc-100 text-sm focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={() => handleAdd(inputVal)}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-bold text-xs rounded-lg transition-colors flex items-center gap-1 cursor-pointer"
        >
          <Plus size={14} />
          <span>Add</span>
        </button>
      </div>

      {/* Package Tags */}
      <div className="flex flex-wrap gap-2 min-h-[38px] p-2 bg-zinc-950 border border-zinc-800/80 rounded-xl">
        {packages.length === 0 ? (
          <span className="text-xs text-zinc-500 italic p-1">No custom APT packages added.</span>
        ) : (
          packages.map((pkg) => (
            <span
              key={pkg}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 font-mono text-xs font-bold"
            >
              <span>{pkg}</span>
              <button
                type="button"
                onClick={() => handleRemove(pkg)}
                className="hover:text-rose-400 cursor-pointer"
              >
                <X size={12} />
              </button>
            </span>
          ))
        )}
      </div>

      {/* Quick suggestions */}
      <div className="flex flex-wrap items-center gap-1.5 pt-1">
        <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider mr-1">Suggestions:</span>
        {COMMON_SUGGESTIONS.filter((s) => !packages.includes(s)).slice(0, 7).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => handleAdd(s)}
            className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
          >
            + {s}
          </button>
        ))}
      </div>
    </div>
  );
}
