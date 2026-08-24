import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Flame, X, Loader2, Check, Boxes } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import BaseImageSelector from './BaseImageSelector';
import BoardSelector from './BoardSelector';
import PackageSelector from './PackageSelector';
import AptRepoManager, { AptRepo } from './AptRepoManager';
import AssetInjector from './AssetInjector';
import ScriptManager from './ScriptManager';
import AdvancedEditor from './AdvancedEditor';
import PartitionEditor, { Partition, DEFAULT_EDGE_BOX_PARTITIONS } from './PartitionEditor';
import CredentialsEditor, { UserAccount } from './CredentialsEditor';
import RepoBrowserModal from './RepoBrowserModal';
import { SearchableSelect } from './SearchableSelect';
import FieldLabel from './FieldLabel';

interface RecipeBuilderModalProps {
  recipe?: any;
  onClose: () => void;
  onSaveSuccess: (recipe: any) => void;
}

const getSystemTimezones = () => {
  const defaults = [
    'UTC',
    'Europe/Moscow',
    'Europe/Kyiv',
    'Europe/London',
    'America/New_York',
    'America/Los_Angeles',
    'Asia/Tokyo',
  ];

  let ianaList: string[] = [];
  try {
    if (typeof Intl !== 'undefined' && (Intl as any).supportedValuesOf) {
      ianaList = (Intl as any).supportedValuesOf('timeZone');
    }
  } catch (err) {
    ianaList = [];
  }

  const allTzs = Array.from(new Set(['UTC', ...ianaList, ...defaults]));
  return allTzs.map((tz) => ({ label: tz, value: tz }));
};

const TIMEZONES = getSystemTimezones();

// C.UTF-8 is built into glibc and needs no locale-gen; the rest require the
// "locales" package in the recipe so locale-gen can compile them.
const LOCALES = [
  'C.UTF-8',
  'en_US.UTF-8',
  'en_GB.UTF-8',
  'ru_RU.UTF-8',
  'uk_UA.UTF-8',
  'de_DE.UTF-8',
  'fr_FR.UTF-8',
  'es_ES.UTF-8',
  'pl_PL.UTF-8',
  'tr_TR.UTF-8',
  'uz_UZ.UTF-8',
  'kk_KZ.UTF-8',
  'zh_CN.UTF-8',
  'C',
  'POSIX',
].map((l) => ({ label: l, value: l }));

export default function RecipeBuilderModal({ recipe, onClose, onSaveSuccess }: RecipeBuilderModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(recipe?.name || '');
  const [description, setDescription] = useState(recipe?.description || '');
  const [distribution, setDistribution] = useState(recipe?.distribution || 'debian');
  const [release, setRelease] = useState(recipe?.release || 'bookworm');
  const [architecture, setArchitecture] = useState(recipe?.architecture || 'amd64');
  const [board, setBoard] = useState(recipe?.board || 'generic');
  const [ignoreMissingArch, setIgnoreMissingArch] = useState(recipe?.ignore_missing_arch_packages || false);
  const [outputFormats, setOutputFormats] = useState<string[]>(recipe?.output_formats || ['raw_xz']);
  const [packages, setPackages] = useState<string[]>(recipe?.packages || []);
  const [repositories, setRepositories] = useState<AptRepo[]>(recipe?.repositories || []);
  const [partitions, setPartitions] = useState<Partition[]>(recipe?.partitions && recipe.partitions.length > 0 ? recipe.partitions : DEFAULT_EDGE_BOX_PARTITIONS);
  const [hostname, setHostname] = useState(recipe?.hostname || 'edge-node');
  const [hostnameFromNetif, setHostnameFromNetif] = useState<boolean>(recipe?.hostname_from_netif || false);
  const [isDev, setIsDev] = useState<boolean>(recipe?.is_dev || false);
  const [locale, setLocale] = useState(recipe?.locale || 'C.UTF-8');
  const [showRepoBrowser, setShowRepoBrowser] = useState(false);
  const [timezone, setTimezone] = useState(recipe?.timezone || 'UTC');
  const [sshKeys, setSshKeys] = useState<string[]>(recipe?.ssh_keys || []);
  const [sshKeyInput, setSshKeyInput] = useState(recipe?.ssh_keys ? recipe.ssh_keys.join('\n') : '');
  const [sshPort, setSshPort] = useState<number>(recipe?.ssh_port ?? 2222);
  const [sshPasswordAuth, setSshPasswordAuth] = useState<boolean>(recipe?.ssh_password_auth ?? true);
  const [sshPermitRootLogin, setSshPermitRootLogin] = useState<boolean>(recipe?.ssh_permit_root_login ?? false);
  const [rootPassword, setRootPassword] = useState(recipe?.root_password || '');
  const [users, setUsers] = useState<UserAccount[]>(recipe?.users || []);
  const [rawMkosiConf, setRawMkosiConf] = useState(recipe?.raw_mkosi_conf || '');
  // preseed.cfg has no editor anymore (mkosi never reads it), but an existing
  // recipe's stored value is preserved unchanged rather than wiped on save.
  const [rawPreseedCfg] = useState(recipe?.raw_preseed_cfg || '');
  const [rawPostinst, setRawPostinst] = useState(recipe?.raw_postinst || '');
  const [rawFirstboot, setRawFirstboot] = useState(recipe?.raw_firstboot || '');
  const [kernelParams, setKernelParams] = useState(recipe?.kernel_params || 'ipv6.disable=1 nohz=off');

  const existingDns = recipe?.network_config?.interfaces?.[0]?.dns;
  const initialDnsStr = Array.isArray(existingDns) && existingDns.length > 0
    ? existingDns.join(' ')
    : '77.88.8.8 1.1.1.1 9.9.9.9 8.8.8.8';
  const [dnsServers, setDnsServers] = useState<string>(initialDnsStr);
  const [ifacePrefix, setIfacePrefix] = useState<string>(recipe?.network_config?.prefix || '');
  const [ifaceStartIndex, setIfaceStartIndex] = useState<number>(
    recipe?.network_config?.start_index ?? 0
  );

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
    const parsedDns = dnsServers.split(/[\s,]+/).map((s: string) => s.trim()).filter((s: string) => s.length > 0);

    const existingNetCfg = recipe?.network_config && typeof recipe.network_config === 'object' ? recipe.network_config : {};
    const existingIfaces = Array.isArray(existingNetCfg.interfaces) && existingNetCfg.interfaces.length > 0 ? existingNetCfg.interfaces : [{ match: "en* eth*", dhcp: true }];
    const updatedIfaces = existingIfaces.map((iface: any, idx: number) => {
      if (idx === 0) {
        return { ...iface, dns: parsedDns };
      }
      return iface;
    });

    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      distribution,
      release,
      architecture,
      board,
      output_formats: distribution === 'armbian' ? outputFormats.filter((f) => f !== 'iso') : outputFormats,
      packages,
      repositories,
      partitions,
      hostname: hostname.trim() || 'edge-node',
      hostname_from_netif: hostnameFromNetif,
      is_dev: isDev,
      ignore_missing_arch_packages: ignoreMissingArch,
      timezone: timezone || 'UTC',
      locale: locale || 'C.UTF-8',
      ssh_keys: parsedKeys,
      ssh_port: sshPort,
      ssh_password_auth: sshPasswordAuth,
      ssh_permit_root_login: sshPermitRootLogin,
      root_password: rootPassword.trim() || null,
      users,
      kernel_params: kernelParams.trim() || null,
      raw_mkosi_conf: rawMkosiConf || null,
      raw_preseed_cfg: rawPreseedCfg || null,
      raw_postinst: rawPostinst || null,
      raw_firstboot: rawFirstboot || null,
      network_config: {
        ...existingNetCfg,
        interfaces: updatedIfaces,
        prefix: ifacePrefix.trim() || null,
        start_index: ifaceStartIndex,
      },
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

  return createPortal(
    <div className="fixed inset-0 z-9999 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-4xl max-h-[90vh] bg-zinc-900 border border-zinc-800 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-modal-in">
        
        {/* Header */}
        <div className="p-6 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
              <Flame size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-zinc-50">{recipe ? t('editRecipe') : t('createRecipe')}</h2>
              <p className="text-xs text-zinc-400">Configure distribution, packages, target OS timezone & build parameters</p>
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
              <FieldLabel hint={t('recipeNameHint') || 'Unique name identifying this recipe. Shown in the recipe list; has no effect on the built image itself.'}>
                {t('recipeName')}
              </FieldLabel>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Edge Gateway Debian 12"
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm focus:outline-hidden"
              />
            </div>
            <div className="space-y-1.5">
              <FieldLabel hint={t('recipeDescriptionHint') || 'Optional free-text notes about this recipe. Not used by the build.'}>
                {t('recipeDescription')}
              </FieldLabel>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional purpose notes..."
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm focus:outline-hidden"
              />
            </div>
          </div>

          {/* Development build marker: renames artifacts to edge-dev_* */}
          <label
            className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer select-none transition-colors ${
              isDev
                ? 'bg-fuchsia-500/10 border-fuchsia-500/40'
                : 'bg-zinc-950 border-zinc-800 hover:border-zinc-700'
            }`}
          >
            <input
              type="checkbox"
              checked={isDev}
              onChange={(e) => setIsDev(e.target.checked)}
              className="w-4 h-4 mt-0.5 rounded-sm border-zinc-800 bg-zinc-950 text-fuchsia-500 focus:ring-fuchsia-500/20"
            />
            <span className="flex-1">
              <span className={`block text-xs font-bold uppercase tracking-wider ${isDev ? 'text-fuchsia-400' : 'text-zinc-400'}`}>
                {t('devBuild') || 'Development Build'}
              </span>
              <span className="block text-[11px] text-zinc-400 mt-0.5">
                {t('devBuildHint') || 'Marks this recipe as a dev build. Artifacts are named'}{' '}
                <code className={`font-mono ${isDev ? 'text-fuchsia-400' : 'text-zinc-500'}`}>
                  {isDev ? 'edge-dev_' : 'edge_'}
                </code>
                {'…'} so dev images cannot be confused with release ones.
              </span>
            </span>
          </label>

          <BaseImageSelector
            distribution={distribution}
            release={release}
            architecture={architecture}
            board={board}
            ignoreMissingArch={ignoreMissingArch}
            onChange={(d, r, a, b) => {
              setDistribution(d);
              setRelease(r);
              setArchitecture(a);
              setBoard(b);
            }}
            onIgnoreMissingArchChange={setIgnoreMissingArch}
          />

          <BoardSelector distribution={distribution} board={board} onChange={setBoard} />

          {/* Output Formats */}
          <div className="space-y-2">
            <FieldLabel hint={t('outputFormatsHint') || '.raw.xz is the flashable disk image itself. .iso is a bootable auto-installer that dd\'s that same image onto a target disk, then removes/ejects the media and powers off.'}>
              {t('outputFormats')}
            </FieldLabel>
            <div className="flex gap-3">
              {[
                { id: 'raw_xz', label: '.raw.xz (Native Disk Image)' },
                // RK3588 (и любая Armbian-плата) грузится через U-Boot в SPI,
                // не через UEFI -- у образа нет ESP, поэтому ISO для неё не
                // строится в принципе (см. build_image.py).
                ...(distribution === 'armbian' ? [] : [{ id: 'iso', label: '.iso (Bootable Installer ISO)' }]),
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
                  <div className={`w-4 h-4 rounded-sm border flex items-center justify-center ${outputFormats.includes(fmt.id) ? 'border-amber-500 bg-amber-500 text-zinc-950' : 'border-zinc-700'}`}>
                    {outputFormats.includes(fmt.id) && <Check size={12} strokeWidth={3} />}
                  </div>
                  <span>{fmt.label}</span>
                </button>
              ))}
            </div>
          </div>

          <PackageSelector packages={packages} onChange={setPackages} />

          {/* Browse packages straight from the configured APT repositories */}
          <button
            type="button"
            onClick={() => setShowRepoBrowser(true)}
            disabled={!recipe?.id || repositories.length === 0}
            title={
              !recipe?.id
                ? 'Save the recipe first to browse its repositories'
                : repositories.length === 0
                ? 'Add an APT repository first'
                : undefined
            }
            className="w-full inline-flex items-center justify-center gap-2 px-3 py-2.5 text-xs font-medium text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 rounded-xl transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Boxes className="w-4 h-4" />
            {t('browseRepository') || 'Browse Repository Packages'}
          </button>

          {showRepoBrowser && (
            <RepoBrowserModal
              recipeId={recipe?.id}
              repositories={repositories}
              selected={packages}
              onClose={() => setShowRepoBrowser(false)}
              onApply={setPackages}
            />
          )}
          <AptRepoManager repositories={repositories} onChange={setRepositories} />
          <PartitionEditor partitions={partitions} onChange={setPartitions} />
          <AssetInjector recipeId={recipe?.id} assets={assets} onUpload={handleAssetUpload} onDelete={handleAssetDelete} />
          <ScriptManager postinstScript={rawPostinst} onChange={setRawPostinst} />

          {/* Hostname & Target OS Timezone */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <FieldLabel hint={t('hostnameHint') || 'Static hostname baked into the image. Ignored at boot if the MAC-address checkbox below is enabled — that overwrites it on first boot instead.'}>
                {t('hostname')}
              </FieldLabel>
              <input
                type="text"
                value={hostname}
                onChange={(e) => setHostname(e.target.value.toLowerCase())}
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm font-mono focus:outline-hidden"
              />
              <label className="flex items-center gap-2 pt-1 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={hostnameFromNetif}
                  onChange={(e) => setHostnameFromNetif(e.target.checked)}
                  className="w-4 h-4 rounded-sm border-zinc-800 bg-zinc-950 text-amber-500 focus:ring-amber-500/20"
                />
                <span className="text-[11px] text-zinc-400 font-medium">
                  Set hostname to active installation port MAC address in post-install (lowercase, no delimiters, e.g. <code className="text-amber-400 font-mono">525400123456</code>)
                </span>
              </label>
            </div>
            <div className="space-y-1.5">
              <FieldLabel hint={t('timezoneHint') || 'IANA timezone name (e.g. Europe/Kyiv). Applied to /etc/localtime and /etc/timezone during the build.'}>
                Target OS Timezone
              </FieldLabel>
              <SearchableSelect
                options={TIMEZONES}
                value={timezone}
                onChange={setTimezone}
              />
              <FieldLabel className="pt-2" hint={t('systemLocaleHint') || 'System LANG. C.UTF-8/C/POSIX are built into glibc and need nothing extra; any other locale requires the "locales" package and is compiled with locale-gen during the build.'}>
                {t('systemLocale') || 'System Locale'}
              </FieldLabel>
              <SearchableSelect
                options={LOCALES}
                value={locale}
                onChange={setLocale}
              />
            </div>
          </div>

          {/* SSH Configuration: Keys + Custom SSH Port */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="sm:col-span-2 space-y-1.5">
              <FieldLabel hint={t('sshKeysHint') || 'One public key per line (ed25519 or rsa). Installed into /root/.ssh/authorized_keys — do not paste a private key here.'}>
                {t('sshKeys')}
              </FieldLabel>
              <textarea
                rows={3}
                value={sshKeyInput}
                onChange={(e) => setSshKeyInput(e.target.value)}
                placeholder={t('sshKeyPlaceholder')}
                className="w-full p-2.5 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs font-mono text-zinc-100 focus:outline-hidden"
              />
            </div>
            <div className="space-y-1.5">
              <FieldLabel hint={t('sshPortHintTip') || 'TCP port sshd listens on. Change this if 22/2222 must stay free for something else on the deployed device.'}>
                {t('sshPort')}
              </FieldLabel>
              <input
                type="number"
                min={1}
                max={65535}
                value={sshPort}
                onChange={(e) => setSshPort(parseInt(e.target.value) || 2222)}
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm font-mono focus:outline-hidden"
              />
              <p className="text-[11px] text-zinc-500">{t('sshPortHint')}</p>
            </div>
          </div>

          {/* SSH access: password login and root-by-password */}
          <div className="space-y-2">
            <label className="flex items-start gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={sshPasswordAuth}
                onChange={(e) => setSshPasswordAuth(e.target.checked)}
                className="w-4 h-4 mt-0.5 rounded-sm border-zinc-800 bg-zinc-950 text-amber-500 focus:ring-amber-500/20"
              />
              <span className="text-[11px] text-zinc-400 font-medium">{t('sshPasswordAuthHint')}</span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={sshPermitRootLogin}
                onChange={(e) => setSshPermitRootLogin(e.target.checked)}
                className="w-4 h-4 mt-0.5 rounded-sm border-zinc-800 bg-zinc-950 text-amber-500 focus:ring-amber-500/20"
              />
              <span className="text-[11px] text-zinc-400 font-medium">{t('sshRootLoginHint')}</span>
            </label>
          </div>

          {/* DNS Configuration */}
          <div className="space-y-1.5">
            <FieldLabel hint={t('dnsServersHintTip') || 'Space-separated DNS nameservers for target OS network interfaces. Defaults to 77.88.8.8 1.1.1.1 9.9.9.9 8.8.8.8.'}>
              {t('dnsServers') || 'DNS Servers'}
            </FieldLabel>
            <input
              type="text"
              value={dnsServers}
              onChange={(e) => setDnsServers(e.target.value)}
              placeholder="77.88.8.8 1.1.1.1 9.9.9.9 8.8.8.8"
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm font-mono focus:outline-hidden"
            />
            <p className="text-[11px] text-zinc-500">{t('dnsServersHint')}</p>
          </div>

          {/* Interface naming: prefix + where numbering starts */}
          <div className="space-y-1.5">
            <FieldLabel hint={t('ifacePrefixHintTip')}>
              {t('ifacePrefix')}
            </FieldLabel>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={ifacePrefix}
                onChange={(e) => setIfacePrefix(e.target.value)}
                placeholder="edge"
                className="flex-1 px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-sm font-mono focus:outline-hidden"
              />
              <div className="flex items-center bg-zinc-950 p-1 rounded-xl border border-zinc-800">
                {[0, 1].map((start) => (
                  <button
                    key={start}
                    type="button"
                    onClick={() => setIfaceStartIndex(start)}
                    className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer ${
                      ifaceStartIndex === start
                        ? 'bg-amber-500 text-zinc-950 shadow-md'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {`${ifacePrefix.trim() || 'edge'}${start}`}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-[11px] text-zinc-500">{t('ifacePrefixHint')}</p>
            {ifacePrefix.trim() && (
              <p className="text-[11px] text-zinc-400 bg-zinc-950/60 border border-zinc-800 rounded-lg px-2.5 py-2 leading-relaxed">
                {t('ifaceFirstPortNote', { name: `${ifacePrefix.trim()}${ifaceStartIndex}` })}
              </p>
            )}
          </div>

          {/* Credentials: root password + additional login accounts */}
          <CredentialsEditor
            rootPassword={rootPassword}
            users={users}
            onRootPasswordChange={setRootPassword}
            onUsersChange={setUsers}
          />

          {/* Kernel Parameters (CMDLINE) */}
          <div className="space-y-1.5">
            <FieldLabel hint={t('kernelParamsHint') || 'Extra space-separated kernel boot arguments, e.g. "quiet loglevel=3". root=, rw, fsck.mode= and console= are added automatically unless you already specify an equivalent, so overriding console= here will not produce duplicates.'}>
              Kernel Parameters (CMDLINE)
            </FieldLabel>
            <input
              type="text"
              value={kernelParams}
              onChange={(e) => setKernelParams(e.target.value)}
              placeholder="e.g. ipv6.disable=1 nohz=off"
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-xs font-mono focus:outline-hidden"
            />
          </div>

          <AdvancedEditor
            rawMkosiConf={rawMkosiConf}
            rawFirstboot={rawFirstboot}
            onChangeMkosi={setRawMkosiConf}
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
    </div>,
    document.body
  );
}
