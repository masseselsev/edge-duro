import React, { useState } from 'react';
import { X, Plus, Package, Cpu, ShieldCheck } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import FieldLabel from './FieldLabel';

interface PackageSelectorProps {
  packages: string[];
  onChange: (packages: string[]) => void;
}

const EDGE_SUGGESTIONS = [
  'edge-base',
  'edge-target-tools',
  'edge-python3-psuctl',
  'edge-timekeeper',
  'edge-zabbix-agent',
  'edge-target-kaskad4',
  'edge-target-puma',
  'edge-target-skif',
  'edge-target-uralan',
  'edge-target-wspaces7',
  'edge-target-wspaces9',
  'edge-target-trc',
  'edge-target-roadeye3',
  'edge-target-edges',
  'edge-target-edges4',
  'edge-mvs',
  'acpi-support-base',
  'dbus-user-session',
  'python3-requests',
];

const STANDARD_SUGGESTIONS = [
  'curl', 'wget', 'vim', 'git', 'nginx', 'openssh-server',
  'systemd-container', 'docker.io', 'htop', 'btop', 'iputils-ping', 'traceroute',
  'dnsutils', 'ethtool', 'tcpdump', 'iperf3', 'sudo', 'ca-certificates',
  'firmware-misc-nonfree', 'intel-media-va-driver-non-free', 'linux-image-amd64', 'net-tools',
];

export default function PackageSelector({ packages, onChange }: PackageSelectorProps) {
  const { t } = useTranslation();
  const [edgeInput, setEdgeInput] = useState('');
  const [stdInput, setStdInput] = useState('');

  const isEdgePackage = (pkg: string) => {
    const lower = pkg.toLowerCase();
    return lower.startsWith('edge-') || [
      'acpi-support-base',
      'dbus-user-session',
      'python3-requests',
    ].includes(lower);
  };

  const edgePackages = packages.filter(isEdgePackage);
  const stdPackages = packages.filter((p) => !isEdgePackage(p));

  const handleAddEdge = (pkgName: string) => {
    const cleaned = pkgName.trim().toLowerCase();
    if (cleaned && !packages.includes(cleaned)) {
      onChange([...packages, cleaned]);
      setEdgeInput('');
    }
  };

  const handleAddStd = (pkgName: string) => {
    const cleaned = pkgName.trim().toLowerCase();
    if (cleaned && !packages.includes(cleaned)) {
      onChange([...packages, cleaned]);
      setStdInput('');
    }
  };

  const handleRemove = (pkgName: string) => {
    onChange(packages.filter((p) => p !== pkgName));
  };

  return (
    <div className="space-y-5 animate-fade-in">
      {/* 1. EDGE SYSTEM PACKAGES CARD */}
      <div className="p-4 rounded-xl bg-zinc-950/90 border border-cyan-500/30 shadow-lg shadow-cyan-950/20 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Cpu size={16} />
            </div>
            <div>
              <FieldLabel
                colorClassName="text-cyan-400"
                hint={
                  t('edgePackagesHint') ||
                  'edge-* packages are fetched directly from your configured repositories and installed with dpkg during the build, bypassing normal APT dependency resolution.'
                }
              >
                {t('edgePackagesTitle') || 'EDGE PLATFORM PACKAGES & DEPENDENCIES'}
              </FieldLabel>
              <p className="text-[11px] text-zinc-400">
                {t('edgePackagesSubtitle') || 'Core Edge platform suite and mandatory runtime dependencies'}
              </p>
            </div>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
            {edgePackages.length} pkgs
          </span>
        </div>

        {/* Input box for Edge packages */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-cyan-500/70">
              <ShieldCheck size={15} />
            </span>
            <input
              type="text"
              value={edgeInput}
              onChange={(e) => setEdgeInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ',') {
                  e.preventDefault();
                  handleAddEdge(edgeInput);
                }
              }}
              placeholder={t('edgePackagePlaceholder') || 'Add Edge package (e.g. edge-base, edge-target-tools)...'}
              className="w-full pl-9 pr-3 py-2 bg-zinc-900/80 border border-cyan-500/20 focus:border-cyan-400 rounded-lg text-zinc-100 text-sm focus:outline-none placeholder-zinc-500 font-mono"
            />
          </div>
          <button
            type="button"
            onClick={() => handleAddEdge(edgeInput)}
            className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 font-bold text-xs rounded-lg transition-colors flex items-center gap-1 cursor-pointer"
          >
            <Plus size={14} />
            <span>Add Edge</span>
          </button>
        </div>

        {/* Edge Package Badges */}
        <div className="flex flex-wrap gap-2 min-h-[38px] p-2.5 bg-zinc-900/50 border border-cyan-500/10 rounded-xl">
          {edgePackages.length === 0 ? (
            <span className="text-xs text-zinc-500 italic p-1">No Edge platform packages selected.</span>
          ) : (
            edgePackages.map((pkg) => (
              <span
                key={pkg}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 font-mono text-xs font-bold shadow-sm"
              >
                <span>{pkg}</span>
                <button
                  type="button"
                  onClick={() => handleRemove(pkg)}
                  className="hover:text-rose-400 cursor-pointer text-cyan-400/70"
                >
                  <X size={12} />
                </button>
              </span>
            ))
          )}
        </div>

        {/* Quick Edge Suggestions */}
        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
          <span className="text-[10px] text-cyan-400/80 font-bold uppercase tracking-wider mr-1">Edge Suite:</span>
          {EDGE_SUGGESTIONS.filter((s) => !packages.includes(s)).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleAddEdge(s)}
              className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/40 hover:bg-cyan-900/60 border border-cyan-500/20 text-cyan-400 hover:text-cyan-200 transition-colors cursor-pointer"
            >
              + {s}
            </button>
          ))}
        </div>
      </div>

      {/* 2. STANDARD SYSTEM & CUSTOM APT PACKAGES CARD */}
      <div className="p-4 rounded-xl bg-zinc-950/90 border border-amber-500/30 shadow-lg shadow-amber-950/10 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400">
              <Package size={16} />
            </div>
            <div>
              <FieldLabel
                colorClassName="text-amber-400"
                hint={
                  t('standardPackagesHint') ||
                  'Regular distribution packages, resolved and installed by APT during the build with automatic dependency resolution -- unlike edge-* packages above.'
                }
              >
                {t('standardPackagesTitle') || 'STANDARD SYSTEM & CUSTOM APT PACKAGES'}
              </FieldLabel>
              <p className="text-[11px] text-zinc-400">
                General distribution utilities, drivers, and user application packages
              </p>
            </div>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold">
            {stdPackages.length} pkgs
          </span>
        </div>

        {/* Input box for Standard packages */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-500">
              <Package size={15} />
            </span>
            <input
              type="text"
              value={stdInput}
              onChange={(e) => setStdInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ',') {
                  e.preventDefault();
                  handleAddStd(stdInput);
                }
              }}
              placeholder={t('packagePlaceholder')}
              className="w-full pl-9 pr-3 py-2 bg-zinc-900/80 border border-zinc-800 focus:border-amber-500 rounded-lg text-zinc-100 text-sm focus:outline-none font-mono"
            />
          </div>
          <button
            type="button"
            onClick={() => handleAddStd(stdInput)}
            className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-bold text-xs rounded-lg transition-colors flex items-center gap-1 cursor-pointer"
          >
            <Plus size={14} />
            <span>Add Package</span>
          </button>
        </div>

        {/* Standard Package Badges */}
        <div className="flex flex-wrap gap-2 min-h-[38px] p-2.5 bg-zinc-900/50 border border-zinc-800/80 rounded-xl">
          {stdPackages.length === 0 ? (
            <span className="text-xs text-zinc-500 italic p-1">No custom system packages selected.</span>
          ) : (
            stdPackages.map((pkg) => (
              <span
                key={pkg}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 font-mono text-xs font-bold"
              >
                <span>{pkg}</span>
                <button
                  type="button"
                  onClick={() => handleRemove(pkg)}
                  className="hover:text-rose-400 cursor-pointer text-amber-500/70"
                >
                  <X size={12} />
                </button>
              </span>
            ))
          )}
        </div>

        {/* Quick Standard Suggestions */}
        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
          <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider mr-1">Suggestions:</span>
          {STANDARD_SUGGESTIONS.filter((s) => !packages.includes(s)).slice(0, 7).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleAddStd(s)}
              className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
            >
              + {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
