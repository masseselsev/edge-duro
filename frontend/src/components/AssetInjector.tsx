import React, { useState } from 'react';
import { Upload, FileText, Trash2, CheckCircle, FileCode } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface AssetInjectorProps {
  recipeId?: number;
  assets: any[];
  onUpload: (file: File, installTarget: string, isPostinst: boolean) => Promise<void>;
  onDelete: (assetId: number) => Promise<void>;
}

export default function AssetInjector({ recipeId, assets, onUpload, onDelete }: AssetInjectorProps) {
  const { t } = useTranslation();
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [targetPath, setTargetPath] = useState('');
  const [isPostinst, setIsPostinst] = useState(false);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setUploading(true);
      try {
        await onUpload(file, targetPath, isPostinst);
      } finally {
        setUploading(false);
      }
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setUploading(true);
      try {
        await onUpload(file, targetPath, isPostinst);
      } finally {
        setUploading(false);
      }
    }
  };

  return (
    <div className="space-y-4">
      <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
        {t('assets')}
      </label>

      {/* Target & Hook Options */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-zinc-950 p-3 rounded-xl border border-zinc-800">
        <input
          type="text"
          value={targetPath}
          onChange={(e) => setTargetPath(e.target.value)}
          placeholder={t('targetPath')}
          className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-100 font-mono focus:border-amber-500"
        />
        <label className="flex items-center gap-2 text-xs text-zinc-300 font-bold cursor-pointer">
          <input
            type="checkbox"
            checked={isPostinst}
            onChange={(e) => setIsPostinst(e.target.checked)}
            className="rounded border-zinc-800 text-amber-500 focus:ring-amber-500 bg-zinc-900"
          />
          <span>{t('postInstall')}</span>
        </label>
      </div>

      {/* Drag & Drop Zone */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-xl p-6 text-center transition-all duration-200 ${
          dragActive
            ? 'border-amber-500 bg-amber-500/10'
            : 'border-zinc-800 bg-zinc-950/50 hover:border-zinc-700'
        }`}
      >
        <input
          type="file"
          id="asset-file-input"
          onChange={handleFileChange}
          className="hidden"
          disabled={uploading || !recipeId}
        />
        <label htmlFor="asset-file-input" className="cursor-pointer space-y-2 block">
          <Upload className="w-8 h-8 text-amber-400 mx-auto" />
          <div className="text-xs font-bold text-zinc-200">{t('dragDropFiles')}</div>
          <div className="text-[10px] text-zinc-500">
            {!recipeId ? 'Save recipe first to enable file uploads.' : 'Allowed: .deb, .sh, .bash, .bin, .tar.gz, .py'}
          </div>
        </label>
      </div>

      {/* Asset File List */}
      {assets && assets.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider">{t('uploadedFiles')}</div>
          <div className="divide-y divide-zinc-800 bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden">
            {assets.map((asset) => (
              <div key={asset.id} className="p-3 flex items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2.5 min-w-0">
                  <FileCode size={16} className="text-amber-400 shrink-0" />
                  <div className="min-w-0">
                    <div className="font-bold text-zinc-200 truncate">{asset.filename}</div>
                    <div className="text-[10px] text-zinc-500 font-mono">
                      {(asset.file_size / 1024).toFixed(1)} KB | Target: {asset.install_target || '/opt/custom/'}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onDelete(asset.id)}
                  className="p-1.5 text-zinc-500 hover:text-rose-400 transition-colors cursor-pointer"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
