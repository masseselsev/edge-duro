import React, { useState, useEffect, useRef } from 'react';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { defaultKeymap } from '@codemirror/commands';
import { oneDark } from '@codemirror/theme-one-dark';
import { Code2 } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import FieldLabel from './FieldLabel';

interface AdvancedEditorProps {
  rawMkosiConf: string;
  rawFirstboot: string;
  onChangeMkosi: (val: string) => void;
  onChangeFirstboot: (val: string) => void;
}

// postinst.sh is intentionally NOT a tab here: it is the exact same
// recipe.raw_postinst field as the "Post-Install Shell Hook" box above
// (ScriptManager), so showing it a second time here just displayed the same
// text in two editors bound to one field. preseed.cfg was removed earlier:
// it is a debian-installer concept mkosi never reads, so it had no effect.
const TABS = [
  { id: 'mkosi', label: 'mkosi.conf' },
  { id: 'firstboot', label: 'firstboot.sh' },
] as const;

export default function AdvancedEditor({
  rawMkosiConf,
  rawFirstboot,
  onChangeMkosi,
  onChangeFirstboot,
}: AdvancedEditorProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'mkosi' | 'firstboot'>('mkosi');
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  const tabHint = (tab: 'mkosi' | 'firstboot') =>
    tab === 'mkosi'
      ? t('mkosiConfHint') ||
        'Raw mkosi.conf lines appended to the generated build config. Advanced/rare: most settings already have a dedicated field above.'
      : t('firstbootHint') ||
        'Shell script that runs once on the DEPLOYED device on its first real boot (not during the build), after ConditionFirstBoot is satisfied.';

  const getCurrentContent = () => (activeTab === 'mkosi' ? rawMkosiConf || '' : rawFirstboot || '');

  const handleContentChange = (content: string) => {
    if (activeTab === 'mkosi') onChangeMkosi(content);
    else onChangeFirstboot(content);
  };

  useEffect(() => {
    if (!editorRef.current) return;

    const startState = EditorState.create({
      doc: getCurrentContent(),
      extensions: [
        keymap.of(defaultKeymap),
        oneDark,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            handleContentChange(update.state.doc.toString());
          }
        }),
      ],
    });

    const view = new EditorView({
      state: startState,
      parent: editorRef.current,
    });

    viewRef.current = view;

    return () => {
      view.destroy();
    };
  }, [activeTab]);

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Code2 size={15} className="text-amber-400" />
          <FieldLabel
            hint={
              t('advancedEditorHint') ||
              'Raw config overrides for advanced cases not covered by a dedicated field. Prefer the fields above when one exists.'
            }
          >
            {t('advancedEditor')}
          </FieldLabel>
        </div>

        <div className="flex bg-zinc-950 p-1 rounded-xl border border-zinc-800 flex-wrap">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              title={tabHint(id)}
              onClick={() => setActiveTab(id)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-mono font-bold transition-all cursor-pointer ${
                activeTab === id ? 'bg-amber-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950">
        <div ref={editorRef} className="min-h-[160px] text-xs font-mono" />
      </div>
    </div>
  );
}
