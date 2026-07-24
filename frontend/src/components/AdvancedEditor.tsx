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
  rawFirstboot: string;
  onChangeMkosi: (val: string) => void;
  onChangePreseed: (val: string) => void;
  onChangePostinst: (val: string) => void;
  onChangeFirstboot: (val: string) => void;
}

export default function AdvancedEditor({
  rawMkosiConf,
  rawPreseedCfg,
  rawPostinst,
  rawFirstboot,
  onChangeMkosi,
  onChangePreseed,
  onChangePostinst,
  onChangeFirstboot
}: AdvancedEditorProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'mkosi' | 'preseed' | 'postinst' | 'firstboot'>('mkosi');
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  const getCurrentContent = () => {
    if (activeTab === 'mkosi') return rawMkosiConf || '';
    if (activeTab === 'preseed') return rawPreseedCfg || '';
    if (activeTab === 'postinst') return rawPostinst || '';
    return rawFirstboot || '';
  };

  const handleContentChange = (content: string) => {
    if (activeTab === 'mkosi') onChangeMkosi(content);
    else if (activeTab === 'preseed') onChangePreseed(content);
    else if (activeTab === 'postinst') onChangePostinst(content);
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
          <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
            {t('advancedEditor')}
          </label>
        </div>

        <div className="flex bg-zinc-950 p-1 rounded-xl border border-zinc-800 flex-wrap">
          {(['mkosi', 'preseed', 'postinst', 'firstboot'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-mono font-bold transition-all cursor-pointer ${
                activeTab === tab ? 'bg-amber-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {tab === 'mkosi' ? 'mkosi.conf' : tab === 'preseed' ? 'preseed.cfg' : tab === 'postinst' ? 'postinst.sh' : 'firstboot.sh'}
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
