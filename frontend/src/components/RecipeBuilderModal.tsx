import React, { useState } from 'react';
import { Flame, X, Loader2, Check } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import BaseImageSelector from './BaseImageSelector';
import PackageSelector from './PackageSelector';
import AptRepoManager, { AptRepo } from './AptRepoManager';
import AssetInjector from './AssetInjector';
import ScriptManager from './ScriptManager';
import AdvancedEditor from './AdvancedEditor';

interface RecipeBuilderModalProps {
  recipe?: any;
  onClose: () => void;
  onSaveSuccess: (recipe: any) => void;
}

export default function RecipeBuilderModal({ recipe, onClose, onSaveSuccess }: RecipeBuilderModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(recipe?.name || '');
  const [description, setDescription] = useState(recipe?.description || '');
  const [distribution, setDistribution] = useState(recipe?.distribution || 'debian');
  const [release, setRelease] = useState(recipe?.release || 'bookworm');
  const [architecture, setArchitecture] = useState(recipe?.architecture || 'amd64');
  const [outputFormats, setOutputFormats] = useState<string[]>(recipe?.output_formats || ['raw_xz']);
  const [packages, setPackages] = useState<string[]>(recipe?.packages || []);
  const [repositories, setRepositories] = useState<AptRepo[]>(recipe?.repositories || []);
  const [hostname, setHostname] = useState(recipe?.hostname || 'edge-node');
  const [sshKeys, setSshKeys] = useState<string[]>(recipe?.ssh_keys || []);
  const [sshKeyInput, setSshKeyInput] = useState(recipe?.ssh_keys ? recipe.ssh_keys.join('\n') : '');
  const [rawMkosiConf, setRawMkosiConf] = useState(recipe?.raw_mkosi_conf || '');
  const [rawPreseedCfg, setRawPreseedCfg] = useState(recipe?.raw_preseed_cfg || '');
  const [rawPostinst, setRawPostinst] = useState(recipe?.raw_postinst || '');
  const [rawFirstboot, setRawFirstboot] = useState(recipe?.raw_firstboot || '');
  const [kernelParams, setKernelParams] = useState(recipe?.kernel_params || 'ipv6.disable=1 nohz=off');

  const [assets, setAssets] = useState<any[]>(recipe?.assets || []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const toggleFormat = (fmt: string) => {
    if (outputFormats.includes(fmt)) {
      if (outputFormats.length > 1) {
        setOutputFormats(outputFormats.filter((f: string) => f !== fmt));
      }
    } else {
      setOutputFormats([...outputFormats, fmt]);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    const parsedKeys = sshKeyInput.split('\n').map((k: string) => k.trim()).filter((k: string) => k.length > 0);

    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      distribution,
      release,
      architecture,
      output_formats: outputFormats,
      packages,
      repositories,
      hostname: hostname.trim() || 'edge-node',
      ssh_keys: parsedKeys,
      kernel_params: kernelParams.trim() || null,
      raw_mkosi_conf: rawMkosiConf || null,
      raw_preseed_cfg: rawPreseedCfg || null,
      raw_postinst: rawPostinst || null,
      raw_firstboot: rawFirstboot || null,
    };

    try {
      const url = recipe ? `/api/recipes/${recipe.id}` : '/api/recipes';
      const method = recipe ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save recipe');
      }

      onSaveSuccess(data);
      onClose();
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setSaving(false);
    }
  };

  const handleAssetUpload = async (file: File, installTarget: string, isPostinst: boolean) => {
    if (!recipe) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('install_target', installTarget);
    formData.append('is_postinst', String(isPostinst));

    try {
      const res = await fetch(`/api/recipes/${recipe.id}/assets`, {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const newAsset = await res.json();
        setAssets([...assets, newAsset]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleAssetDelete = async (assetId: number) => {
    try {
      const res = await fetch(`/api/assets/${assetId}`, { method: 'DELETE' });
      if (res.ok) {
        setAssets(assets.filter((a: any) => a.id !== assetId));
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-4xl max-h-[90vh] bg-zinc-900 border border-zinc-800 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-modal-in">
        
        {/* Header */}
        <div className="p-6 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
              <Flame size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-zinc-50">{recipe ? t('editRecipe') : t('createRecipe')}</h2>
              <p className="text-xs text-zinc-400">Configure distribution, packages, custom mirrors & build parameters</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer">
            <X size={20} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSave} className="flex-1 overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl text-xs font-semibold">
              {error}
            </div>
          )}

          {/* Basic Info */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">{t('recipeName')}</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Edge Gateway Debian 12"
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm focus:outline-none"
              />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">{t('recipeDescription')}</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional purpose notes..."
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm focus:outline-none"
              />
            </div>
          </div>

          <BaseImageSelector
            distribution={distribution}
            release={release}
            architecture={architecture}
            onChange={(d, r, a) => {
              setDistribution(d);
              setRelease(r);
              setArchitecture(a);
            }}
          />

          {/* Output Formats */}
          <div className="space-y-2">
            <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">{t('outputFormats')}</label>
            <div className="flex gap-3">
              {[
                { id: 'raw_xz', label: '.raw.xz (Native Disk Image)' },
                { id: 'iso', label: '.iso (Bootable Installer ISO)' }
              ].map((fmt) => (
                <button
                  key={fmt.id}
                  type="button"
                  onClick={() => toggleFormat(fmt.id)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                    outputFormats.includes(fmt.id)
                      ? 'bg-amber-500/10 border-amber-500 text-amber-400'
                      : 'bg-zinc-950 border-zinc-800 text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  <div className={`w-4 h-4 rounded border flex items-center justify-center ${outputFormats.includes(fmt.id) ? 'border-amber-500 bg-amber-500 text-zinc-950' : 'border-zinc-700'}`}>
                    {outputFormats.includes(fmt.id) && <Check size={12} strokeWidth={3} />}
                  </div>
                  <span>{fmt.label}</span>
                </button>
              ))}
            </div>
          </div>

          <PackageSelector packages={packages} onChange={setPackages} />
          <AptRepoManager repositories={repositories} onChange={setRepositories} />
          <AssetInjector recipeId={recipe?.id} assets={assets} onUpload={handleAssetUpload} onDelete={handleAssetDelete} />
          <ScriptManager postinstScript={rawPostinst} onChange={setRawPostinst} />

          {/* Hostname & SSH Keys */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">{t('hostname')}</label>
              <input
                type="text"
                value={hostname}
                onChange={(e) => setHostname(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm font-mono focus:outline-none"
              />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">{t('sshKeys')}</label>
              <textarea
                rows={3}
                value={sshKeyInput}
                onChange={(e) => setSshKeyInput(e.target.value)}
                placeholder={t('sshKeyPlaceholder')}
                className="w-full p-2.5 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs font-mono text-zinc-100 focus:outline-none"
              />
            </div>
          </div>

          {/* Kernel Parameters (CMDLINE) */}
          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
              Kernel Parameters (CMDLINE)
            </label>
            <input
              type="text"
              value={kernelParams}
              onChange={(e) => setKernelParams(e.target.value)}
              placeholder="e.g. ipv6.disable=1 nohz=off"
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-xs font-mono focus:outline-none"
            />
          </div>

          <AdvancedEditor
            rawMkosiConf={rawMkosiConf}
            rawPreseedCfg={rawPreseedCfg}
            rawPostinst={rawPostinst}
            rawFirstboot={rawFirstboot}
            onChangeMkosi={setRawMkosiConf}
            onChangePreseed={setRawPreseedCfg}
            onChangePostinst={setRawPostinst}
            onChangeFirstboot={setRawFirstboot}
          />
        </form>

        {/* Footer */}
        <div className="p-4 border-t border-zinc-800 flex justify-end gap-3 bg-zinc-950/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2.5 text-xs font-bold text-zinc-400 bg-zinc-800/50 hover:bg-zinc-800 rounded-xl transition-colors cursor-pointer"
          >
            {t('cancel')}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 text-xs font-bold text-zinc-950 bg-amber-500 hover:bg-amber-400 rounded-xl disabled:opacity-50 transition-colors flex items-center gap-1.5 cursor-pointer shadow-lg shadow-amber-500/10"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            <span>{t('save')}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
