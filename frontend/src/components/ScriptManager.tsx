import React from 'react';
import { Terminal } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import FieldLabel from './FieldLabel';

interface ScriptManagerProps {
  postinstScript: string;
  onChange: (script: string) => void;
}

export default function ScriptManager({ postinstScript, onChange }: ScriptManagerProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Terminal size={15} className="text-amber-400" />
        <FieldLabel
          hint={
            t('postinstHint') ||
            'Shell commands that run once, inside a chroot of the rootfs, during the BUILD (not on the deployed device). Use it for one-off setup baked into the image: enabling a service, writing a config file, etc.'
          }
        >
          Post-Install Shell Hook (`mkosi.postinst.chroot`)
        </FieldLabel>
      </div>

      <textarea
        value={postinstScript || ''}
        onChange={(e) => onChange(e.target.value)}
        rows={5}
        placeholder={`#!/bin/bash\n# Custom commands to run inside rootfs chroot during build phase\nsystemctl enable nginx\nuseradd -m -s /bin/bash edgeadmin`}
        className="w-full p-3 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs font-mono text-zinc-100 focus:outline-none leading-relaxed"
      />
    </div>
  );
}
