import React from 'react';
import { X, PackageX } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface MissingPackage {
  name: string;
  source: string;
  reason: string;
  detail?: string;
}

interface MissingPackagesModalProps {
  build: any;
  onClose: () => void;
}

export default function MissingPackagesModal({ build, onClose }: MissingPackagesModalProps) {
  const { t } = useTranslation();
  const items: MissingPackage[] = build.missing_packages || [];
  const arch = build.recipe?.architecture || '';

  const reasonLabel = (reason: string) => {
    if (reason === 'critical') return t('missingPkgsReasonCritical');
    if (reason === 'dependency') return t('missingPkgsReasonDependency');
    return t('missingPkgsReasonNotInIndex');
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
      onClick={onClose}
    >
      <div
        className="bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <h3 className="flex items-center gap-2 text-sm font-bold text-zinc-100">
            <PackageX size={16} className="text-amber-400" />
            {t('missingPkgsTitle').replace('{arch}', arch)}
          </h3>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-4 space-y-2">
          {items.map((pkg) => (
            <div
              key={`${pkg.name}-${pkg.reason}`}
              className="rounded-xl border border-zinc-800 bg-zinc-950 px-4 py-3"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-xs font-bold text-zinc-100">{pkg.name}</span>
                <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                  {pkg.source === 'edge' ? t('missingPkgsSourceEdge') : t('missingPkgsSourceApt')}
                </span>
              </div>
              <div className="mt-1 text-[11px] text-zinc-400">{reasonLabel(pkg.reason)}</div>
              {pkg.detail && (
                <pre className="mt-2 overflow-x-auto rounded-lg bg-black/40 px-3 py-2 font-mono text-[10px] text-zinc-500">
                  {pkg.detail}
                </pre>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
