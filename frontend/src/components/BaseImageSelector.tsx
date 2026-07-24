import React from 'react';
import { useTranslation } from '../context/TranslationContext';

interface BaseImageSelectorProps {
  distribution: string;
  release: string;
  architecture: string;
  onChange: (distro: string, release: string, arch: string) => void;
}

const IMAGES = [
  { distro: 'debian', release: 'bookworm', name: 'Debian 12 (Bookworm)', tag: 'LTS' },
  { distro: 'debian', release: 'trixie', name: 'Debian 13 (Trixie)', tag: 'Stable' },
  { distro: 'debian', release: 'forky', name: 'Debian 14 (Forky)', tag: 'Testing' },
  { distro: 'ubuntu', release: 'resolute', name: 'Ubuntu 26.04 (Resolute Raccoon)', tag: 'LTS' },
  { distro: 'ubuntu', release: 'noble', name: 'Ubuntu 24.04 (Noble Numbat)', tag: 'LTS' },
  { distro: 'ubuntu', release: 'jammy', name: 'Ubuntu 22.04 (Jammy Jellyfish)', tag: 'LTS' },
];

export default function BaseImageSelector({ distribution, release, architecture, onChange }: BaseImageSelectorProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
          {t('baseImage')}
        </label>
        
        {/* Architecture Pill Selector */}
        <div className="flex items-center bg-zinc-950 p-1 rounded-xl border border-zinc-800">
          {['amd64', 'arm64'].map((arch) => (
            <button
              key={arch}
              type="button"
              onClick={() => onChange(distribution, release, arch)}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer ${
                architecture === arch
                  ? 'bg-amber-500 text-zinc-950 shadow-md'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {arch}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {IMAGES.map((img) => {
          const isSelected = distribution === img.distro && release === img.release;
          return (
            <button
              key={`${img.distro}-${img.release}`}
              type="button"
              onClick={() => onChange(img.distro, img.release, architecture)}
              className={`p-4 rounded-xl border text-left transition-all duration-200 cursor-pointer ${
                isSelected
                  ? 'bg-amber-500/10 border-amber-500 text-zinc-50 shadow-lg shadow-amber-500/10'
                  : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-amber-400">
                  {img.distro}
                </span>
                <span className="text-[10px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded-full font-mono">
                  {img.tag}
                </span>
              </div>
              <div className="text-sm font-bold">{img.name}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
