import React from 'react';
import { useTranslation } from '../context/TranslationContext';
import FieldLabel from './FieldLabel';

interface BoardSelectorProps {
  distribution: string;
  board: string;
  onChange: (board: string) => void;
}

// Board-specific fixes (firmware, DTB, U-Boot) are gated on this exact key in
// the backend (see core/workspace.py, core/packages.py) -- listing a board
// here without wiring it up there would leave it selectable but silently
// non-functional. `ready: false` keeps a placeholder visible without letting
// anyone actually pick a board with no backend support yet.
// Exported so other views (e.g. the recipe card grid in RecipesTab) can
// resolve a stored board id to its display name without duplicating this list.
export const BOARDS = [
  { id: 'opi5-plus', name: 'Orange Pi 5 Plus', soc: 'RK3588', ready: true },
  { id: 'nanopc-t6-lts', name: 'NanoPC-T6 LTS', soc: 'RK3588', ready: false },
];

export default function BoardSelector({ distribution, board, onChange }: BoardSelectorProps) {
  const { t } = useTranslation();

  // Only Armbian recipes are ever RK3588 boards -- Debian/Ubuntu builds are
  // amd64 and have no board concept at all (see architecture_for_distribution
  // in core/packages.py).
  if (distribution !== 'armbian') return null;

  return (
    <div className="space-y-2">
      <FieldLabel hint={t('targetBoardHint')}>{t('targetBoard')}</FieldLabel>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {BOARDS.map((b) => {
          const isSelected = board === b.id;
          return (
            <label
              key={b.id}
              className={`flex items-center gap-3 p-4 rounded-xl border transition-all duration-200 ${
                b.ready ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
              } ${
                isSelected
                  ? 'bg-amber-500/10 border-amber-500 text-zinc-50 shadow-lg shadow-amber-500/10'
                  : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
              }`}
            >
              <input
                type="radio"
                name="target-board"
                value={b.id}
                checked={isSelected}
                disabled={!b.ready}
                onChange={() => onChange(b.id)}
                className="w-3.5 h-3.5 border-zinc-700 bg-zinc-950 text-amber-500 focus:ring-amber-500/40 cursor-pointer disabled:cursor-not-allowed"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-bold truncate">{b.name}</span>
                  {!b.ready && (
                    <span className="shrink-0 text-[10px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded-full font-mono">
                      {t('boardComingSoon')}
                    </span>
                  )}
                </div>
                <span className="text-xs font-mono text-amber-400">{b.soc}</span>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
