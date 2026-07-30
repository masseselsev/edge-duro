import React, { useState } from 'react';
import { HardDrive, Plus, Trash2, RotateCcw, Database } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

export interface Partition {
  mountpoint: string;
  size: string;
  filesystem: string;
  type: string;
  label?: string;
}

interface PartitionEditorProps {
  partitions: Partition[];
  onChange: (partitions: Partition[]) => void;
}

export const DEFAULT_EDGE_BOX_PARTITIONS: Partition[] = [
  { mountpoint: '/boot', size: '512M', filesystem: 'vfat', type: 'esp', label: 'edgeboot' },
  { mountpoint: '/', size: '8G', filesystem: 'ext4', type: 'root', label: 'edgeroot' },
  { mountpoint: '/var/log/edge', size: '1G', filesystem: 'ext4', type: 'generic', label: 'edgelog' },
  { mountpoint: '/var/opt/edge', size: 'max', filesystem: 'ext4', type: 'generic', label: 'edgestor' },
];

export default function PartitionEditor({ partitions, onChange }: PartitionEditorProps) {
  const { t } = useTranslation();

  const [newMount, setNewMount] = useState('/');
  const [newSize, setNewSize] = useState('2G');
  const [newFs, setNewFs] = useState('ext4');
  const [newType, setNewType] = useState('root');
  const [newLabel, setNewLabel] = useState('');

  const currentPartitions = partitions && partitions.length > 0 ? partitions : DEFAULT_EDGE_BOX_PARTITIONS;

  const handleApplyPreset = () => {
    onChange(DEFAULT_EDGE_BOX_PARTITIONS);
  };

  const handleAddPartition = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMount.trim()) return;

    const newPart: Partition = {
      mountpoint: newMount.trim(),
      size: newSize.trim() || '2G',
      filesystem: newFs,
      type: newType,
      label: newLabel.trim() || undefined,
    };

    onChange([...currentPartitions, newPart]);
    setNewMount('');
    setNewSize('2G');
    setNewLabel('');
  };

  const handleRemovePartition = (index: number) => {
    const updated = currentPartitions.filter((_, i) => i !== index);
    onChange(updated);
  };

  const handleUpdatePartition = (index: number, field: keyof Partition, value: string) => {
    const updated = currentPartitions.map((p, i) => {
      if (i === index) {
        return { ...p, [field]: value };
      }
      return p;
    });
    onChange(updated);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header & Preset Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-900/60 border border-slate-800">
        <div>
          <div className="flex items-center gap-2 font-semibold text-slate-200">
            <HardDrive className="w-5 h-5 text-sky-400" />
            <span>{t('partitionLayout') || 'Disk Partition Layout'}</span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t('partitionSubtitle') || 'Configure target storage partitions for system, logs, and data'}
          </p>
        </div>

        <button
          type="button"
          onClick={handleApplyPreset}
          className="inline-flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-amber-400 hover:text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 rounded-lg transition-colors cursor-pointer"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>{t('presetEdgeBox') || 'Apply Edge D.U.R.O. Standard (edge-box)'}</span>
        </button>
      </div>

      {/* Partitions List */}
      <div className="space-y-3">
        {currentPartitions.map((part, index) => (
          <div
            key={index}
            className="grid grid-cols-1 sm:grid-cols-12 gap-3 p-3.5 rounded-xl bg-slate-900/40 border border-slate-800/80 items-center hover:border-slate-700 transition-colors animate-modal-in"
          >
            {/* Mount Point */}
            <div className="sm:col-span-3">
              <label
                title={t('mountPointHint') || 'Where this partition is mounted in the running system, e.g. / or /var/log/edge. Must match an entry generated in /etc/fstab.'}
                className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
              >
                {t('mountPoint') || 'Mount Point'}
              </label>
              <input
                type="text"
                value={part.mountpoint}
                onChange={(e) => handleUpdatePartition(index, 'mountpoint', e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                placeholder="/"
              />
            </div>

            {/* Type */}
            <div className="sm:col-span-2">
              <label
                title={t('partitionTypeHint') || 'esp = EFI System Partition, required for UEFI boot. root = the / filesystem. generic = any other mount. swap = swap space.'}
                className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
              >
                {t('partitionType') || 'Type'}
              </label>
              <select
                value={part.type}
                onChange={(e) => handleUpdatePartition(index, 'type', e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 cursor-pointer"
              >
                <option value="esp">ESP (EFI)</option>
                <option value="root">Root (/)</option>
                <option value="generic">Data (generic)</option>
                <option value="swap">Swap</option>
              </select>
            </div>

            {/* Filesystem */}
            <div className="sm:col-span-2">
              <label
                title={t('fileSystemHint') || 'Filesystem to format the partition with. vfat is required for the ESP; swap has no filesystem.'}
                className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
              >
                {t('fileSystem') || 'Filesystem'}
              </label>
              <select
                value={part.filesystem}
                onChange={(e) => handleUpdatePartition(index, 'filesystem', e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 cursor-pointer font-mono"
              >
                <option value="ext4">ext4</option>
                <option value="vfat">vfat</option>
                <option value="ext2">ext2</option>
                <option value="xfs">xfs</option>
                <option value="swap">swap</option>
              </select>
            </div>

            {/* Size */}
            <div className="sm:col-span-2">
              <label
                title={t('partitionSizeHint') || 'e.g. 512M, 8G. Use "max" on the LAST partition to take all remaining disk space -- only meaningful there.'}
                className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
              >
                {t('partitionSize') || 'Size'}
              </label>
              <input
                type="text"
                value={part.size}
                onChange={(e) => handleUpdatePartition(index, 'size', e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                placeholder="2G / max"
              />
            </div>

            {/* Label */}
            <div className="sm:col-span-2">
              <label
                title={t('partitionLabelHint') || 'Filesystem label, e.g. edgeroot. Referenced by /etc/fstab and the boot entry (root=LABEL=...), so it must be unique on the disk.'}
                className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
              >
                {t('partitionLabel') || 'Label'}
              </label>
              <input
                type="text"
                value={part.label || ''}
                onChange={(e) => handleUpdatePartition(index, 'label', e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                placeholder="edgeroot"
              />
            </div>

            {/* Actions */}
            <div className="sm:col-span-1 flex justify-end pt-4 sm:pt-0">
              <button
                type="button"
                onClick={() => handleRemovePartition(index)}
                className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
                title={t('delete') || 'Delete'}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Add Custom Partition Form */}
      <form onSubmit={handleAddPartition} className="p-4 rounded-xl bg-slate-950/40 border border-dashed border-slate-800 space-y-3">
        <div className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
          <Plus className="w-4 h-4 text-sky-400" />
          <span>{t('addPartition') || 'Add Partition'}</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
          <input
            type="text"
            value={newMount}
            onChange={(e) => setNewMount(e.target.value)}
            placeholder="/var/custom"
            title="Mount point for the new partition, e.g. /var/custom"
            className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
          />

          <select
            value={newType}
            onChange={(e) => setNewType(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 cursor-pointer"
          >
            <option value="generic">Data (generic)</option>
            <option value="root">Root (/)</option>
            <option value="esp">ESP (EFI)</option>
            <option value="swap">Swap</option>
          </select>

          <select
            value={newFs}
            onChange={(e) => setNewFs(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 cursor-pointer font-mono"
          >
            <option value="ext4">ext4</option>
            <option value="vfat">vfat</option>
            <option value="ext2">ext2</option>
            <option value="xfs">xfs</option>
            <option value="swap">swap</option>
          </select>

          <input
            type="text"
            value={newSize}
            onChange={(e) => setNewSize(e.target.value)}
            placeholder="1G / max"
            title='Size, e.g. 1G. "max" only makes sense on the last partition.'
            className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
          />

          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label (optional)"
            title="Filesystem label, referenced by fstab and the boot entry. Must be unique on the disk."
            className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
          />
        </div>

        <div className="flex justify-end pt-1">
          <button
            type="submit"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-sky-400 hover:text-sky-300 bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 rounded-lg transition-colors cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{t('addPartition') || 'Add Partition'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
