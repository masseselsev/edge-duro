import React from 'react';
import { createPortal } from 'react-dom';
import { Flame, X, Cpu, Package, Database, HardDrive, Clock, Terminal, Globe, Key } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface RecipeViewerModalProps {
  recipe: any;
  onClose: () => void;
}

export default function RecipeViewerModal({ recipe, onClose }: RecipeViewerModalProps) {
  const { t } = useTranslation();

  if (!recipe) return null;

  const edgePackages = (recipe.packages || []).filter((p: string) => p.startsWith('edge-'));
  const standardPackages = (recipe.packages || []).filter((p: string) => !p.startsWith('edge-'));

  const modalContent = (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-zinc-950/80 backdrop-blur-md animate-fade-in">
      <div className="bg-zinc-900 border border-zinc-800 rounded-3xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-modal-in">
        
        {/* Header */}
        <div className="p-6 border-b border-zinc-800 flex items-center justify-between gap-4 bg-zinc-950/50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-2xl">
              <Flame size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-zinc-50 tracking-tight">{recipe.name}</h2>
                <span className="text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2.5 py-0.5 rounded-full font-mono font-bold">
                  {recipe.distribution} {recipe.release}
                </span>
                <span className="text-[10px] bg-zinc-800 text-zinc-300 border border-zinc-700 px-2 py-0.5 rounded-full font-mono font-bold">
                  {recipe.architecture}
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5 line-clamp-1">
                {recipe.description || t('noDescription')}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-xl transition-colors cursor-pointer"
          >
            <X size={20} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="p-6 space-y-6 overflow-y-auto custom-scrollbar flex-1 text-xs">
          
          {/* System Specs Overview */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 bg-zinc-950/50 p-4 border border-zinc-800/80 rounded-2xl">
            <div>
              <span className="text-zinc-500 font-bold uppercase text-[10px] block">Hostname</span>
              <span className="font-mono text-zinc-200 font-bold">
                {recipe.hostname_from_netif ? 'MAC Address (netif)' : recipe.hostname || 'edge-node'}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 font-bold uppercase text-[10px] block">SSH Port</span>
              <span className="font-mono text-cyan-400 font-bold">
                {recipe.ssh_port || 2222}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 font-bold uppercase text-[10px] block">Output Formats</span>
              <span className="font-mono text-amber-400 font-bold">
                {(recipe.output_formats || []).join(', ').toUpperCase()}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 font-bold uppercase text-[10px] block">Timezone</span>
              <span className="font-mono text-zinc-300 font-semibold">{recipe.timezone || 'UTC'}</span>
            </div>
            <div>
              <span className="text-zinc-500 font-bold uppercase text-[10px] block">Total Packages</span>
              <span className="font-mono text-emerald-400 font-bold">{(recipe.packages || []).length} pkgs</span>
            </div>
          </div>

          {/* Edge Suite & Platform Packages */}
          {edgePackages.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-cyan-400 font-bold">
                <Package size={15} />
                <span>Edge Target Platform Packages ({edgePackages.length})</span>
              </div>
              <div className="flex flex-wrap gap-1.5 p-3 bg-cyan-950/20 border border-cyan-500/20 rounded-2xl">
                {edgePackages.map((pkg: string) => (
                  <span
                    key={pkg}
                    className="px-2.5 py-1 bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 rounded-lg font-mono font-bold text-[11px]"
                  >
                    {pkg}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Standard Distribution Packages */}
          {standardPackages.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-amber-400 font-bold">
                <Package size={15} />
                <span>Distribution Base Packages ({standardPackages.length})</span>
              </div>
              <div className="flex flex-wrap gap-1.5 p-3 bg-zinc-950/60 border border-zinc-800 rounded-2xl max-h-36 overflow-y-auto custom-scrollbar">
                {standardPackages.map((pkg: string) => (
                  <span
                    key={pkg}
                    className="px-2 py-0.5 bg-zinc-800/80 text-zinc-300 border border-zinc-700/60 rounded font-mono text-[11px]"
                  >
                    {pkg}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Custom APT Repositories */}
          {recipe.repositories && recipe.repositories.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-indigo-400 font-bold">
                <Globe size={15} />
                <span>Configured Repositories ({recipe.repositories.length})</span>
              </div>
              <div className="space-y-2">
                {recipe.repositories.map((repo: any, idx: number) => (
                  <div key={idx} className="p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl space-y-1 font-mono">
                    <div className="flex items-center justify-between text-zinc-200 font-bold">
                      <span>{repo.name}</span>
                      <span className="text-zinc-500 text-[10px]">{repo.suite} / {repo.components}</span>
                    </div>
                    <div className="text-amber-400/90 text-[11px] truncate">{repo.url}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Kernel Parameters */}
          {recipe.kernel_params && (
            <div className="space-y-1.5">
              <span className="text-zinc-400 font-bold">Kernel Command Line Parameters:</span>
              <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl font-mono text-zinc-300">
                {recipe.kernel_params}
              </div>
            </div>
          )}

          {/* Postinst Script Snippet */}
          {recipe.raw_postinst && (
            <div className="space-y-1.5">
              <span className="text-zinc-400 font-bold">Chroot Post-Install Script (mkosi.postinst):</span>
              <pre className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl font-mono text-emerald-400 max-h-36 overflow-y-auto custom-scrollbar text-[11px]">
                {recipe.raw_postinst}
              </pre>
            </div>
          )}

          {/* Firstboot Script Snippet */}
          {recipe.raw_firstboot && (
            <div className="space-y-1.5">
              <span className="text-zinc-400 font-bold">First Boot Initialization Script (mkosi.finalize):</span>
              <pre className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl font-mono text-amber-400 max-h-36 overflow-y-auto custom-scrollbar text-[11px]">
                {recipe.raw_firstboot}
              </pre>
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-zinc-800 flex items-center justify-end gap-3 bg-zinc-950/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-bold text-xs rounded-xl transition-colors cursor-pointer"
          >
            {t('close')}
          </button>
        </div>

      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
