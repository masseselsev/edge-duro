import React from 'react';
import { useTranslation } from '../context/TranslationContext';
import FieldLabel from './FieldLabel';

interface BaseImageSelectorProps {
  distribution: string;
  release: string;
  architecture: string;
  board: string;
  ignoreMissingArch: boolean;
  onChange: (distro: string, release: string, arch: string, board: string) => void;
  onIgnoreMissingArchChange: (value: boolean) => void;
}

// Архитектуру не выбирают отдельно -- она следует из образа: Armbian
// существует только под arm64-платы, Debian и Ubuntu мы собираем под amd64.
const IMAGES = [
  { distro: 'debian', release: 'bookworm', name: 'Debian 12 (Bookworm)', tag: 'LTS', arch: 'amd64', board: 'generic' },
  { distro: 'debian', release: 'trixie', name: 'Debian 13 (Trixie)', tag: 'Stable', arch: 'amd64', board: 'generic' },
  { distro: 'debian', release: 'forky', name: 'Debian 14 (Forky)', tag: 'Testing', arch: 'amd64', board: 'generic' },
  { distro: 'ubuntu', release: 'resolute', name: 'Ubuntu 26.04 (Resolute Raccoon)', tag: 'LTS', arch: 'amd64', board: 'generic' },
  { distro: 'ubuntu', release: 'noble', name: 'Ubuntu 24.04 (Noble Numbat)', tag: 'LTS', arch: 'amd64', board: 'generic' },
  { distro: 'ubuntu', release: 'jammy', name: 'Ubuntu 22.04 (Jammy Jellyfish)', tag: 'LTS', arch: 'amd64', board: 'generic' },
  { distro: 'armbian', release: 'noble', name: 'Armbian / Ubuntu 24.04 — Orange Pi 5 Plus', tag: 'RK3588', arch: 'arm64', board: 'opi5-plus' },
  { distro: 'armbian', release: 'bookworm', name: 'Armbian / Debian 12 — Orange Pi 5 Plus', tag: 'RK3588', arch: 'arm64', board: 'opi5-plus' },
];

export default function BaseImageSelector({
  distribution,
  release,
  architecture,
  board,
  ignoreMissingArch,
  onChange,
  onIgnoreMissingArchChange,
}: BaseImageSelectorProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
          {t('baseImage')}
        </label>
        
        {/* Архитектура выводится из выбранного образа, а не задаётся вручную. */}
        <span className="px-3 py-1 rounded-lg text-xs font-mono font-bold bg-zinc-950 border border-zinc-800 text-amber-400">
          {architecture}
        </span>
      </div>

      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={ignoreMissingArch}
          onChange={(e) => onIgnoreMissingArchChange(e.target.checked)}
          className="w-3.5 h-3.5 rounded-sm border-zinc-700 bg-zinc-950 text-amber-500 focus:ring-amber-500/40 cursor-pointer"
        />
        <FieldLabel
          hint={t('ignoreMissingArchPkgsHint')}
          className="normal-case tracking-normal font-normal cursor-pointer"
        >
          {t('ignoreMissingArchPkgs')}
        </FieldLabel>
      </label>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {IMAGES.map((img) => {
          const isSelected =
            distribution === img.distro && release === img.release && board === img.board;
          return (
            <button
              key={`${img.distro}-${img.release}-${img.board}`}
              type="button"
              onClick={() => onChange(img.distro, img.release, img.arch, img.board)}
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
