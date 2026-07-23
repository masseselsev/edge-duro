import React, { useState, useEffect, useRef } from 'react';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { defaultKeymap } from '@codemirror/commands';
import { oneDark } from '@codemirror/theme-one-dark';
import { Code2 } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface AdvancedEditorProps {
  rawMkosiConf: string;
  rawPreseedCfg: string;
  rawPostinst: string;
  onChangeMkosi: (val: string) => void;
  onChangePreseed: (val: string) => void;
  onChangePostinst: (val: string) => void;
}

export default function AdvancedEditor({
  rawMkosiConf,
  rawPreseedCfg,
  rawPostinst,
  onChangeMkosi,
  onChangePreseed,
  onChangePostinst
}: AdvancedEditorProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'mkosi' | 'preseed' | 'postinst'>('mkosi');
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  const getCurrentContent = () => {
    if (activeTab === 'mkosi') return rawMkosiConf || '';
    if (activeTab === 'preseed') return rawPreseedCfg || '';
    return rawPostinst || '';
  };

  const handleContentChange = (content: string) => {
    if (activeTab === 'mkosi') onChangeMkosi(content);
    else if (activeTab === 'preseed') onChangePreseed(content);
    else onChangePostinst(content);
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
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Code2 size={15} className="text-amber-400" />
          <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
            {t('advancedEditor')}
          </label>
        </div>

        <div className="flex bg-zinc-950 p-1 rounded-xl border border-zinc-800">
          {(['mkosi', 'preseed', 'postinst'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer ${
                activeTab === tab ? 'bg-amber-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {tab === 'mkosi' ? 'mkosi.conf' : tab === 'preseed' ? 'preseed.cfg' : 'postinst'}
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
