import React, { useState, useEffect, useRef } from 'react';
import { Terminal, X, Circle, Download } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface BuildLogStreamProps {
  buildId: string;
  recipeName?: string;
  onClose: () => void;
}

export default function BuildLogStream({ buildId, recipeName, onClose }: BuildLogStreamProps) {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<string[]>([]);
  const [status, setStatus] = useState<string>('RUNNING');
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Initial fetch of existing log output
    fetch(`/api/builds/${buildId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.log_output) {
          setLogs(data.log_output.split('\n'));
        }
        if (data.status) {
          setStatus(data.status);
        }
      })
      .catch((err) => console.error(err));

    // Connect SSE stream
    const eventSource = new EventSource(`/api/builds/${buildId}/stream`);

    eventSource.addEventListener('log', (event: MessageEvent) => {
      setLogs((prev) => [...prev, event.data]);
    });

    eventSource.onerror = (err) => {
      console.warn('SSE stream disconnected or ended:', err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [buildId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-5xl h-[85vh] bg-zinc-950 border border-zinc-800 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-modal-in">
        
        {/* Header */}
        <div className="p-4 px-6 border-b border-zinc-900 flex items-center justify-between bg-zinc-900/60">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
              <Terminal size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-zinc-100">
                  Build Console — {recipeName || buildId.slice(0, 8)}
                </h3>
                <span className="flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800">
                  <Circle
                    size={8}
                    className={
                      status === 'RUNNING' ? 'text-amber-400 fill-amber-400 animate-pulse' :
                      status === 'SUCCESS' ? 'text-emerald-400 fill-emerald-400' :
                      'text-rose-400 fill-rose-400'
                    }
                  />
                  <span className="font-bold text-zinc-300">{status}</span>
                </span>
              </div>
              <p className="text-[10px] text-zinc-500 font-mono">ID: {buildId}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <a
              href={`/api/builds/${buildId}/download`}
              className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg text-xs font-bold text-zinc-300 transition-colors flex items-center gap-1.5"
            >
              <Download size={13} />
              <span>{t('downloadArtifact')}</span>
            </a>
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Monospace Log Viewer */}
        <div className="flex-1 p-5 overflow-y-auto font-mono text-xs text-zinc-300 space-y-1 bg-zinc-950 leading-relaxed">
          {logs.length === 0 ? (
            <div className="text-zinc-600 italic">Waiting for live build output stream...</div>
          ) : (
            logs.map((line, i) => (
              <div
                key={i}
                className={
                  line.includes('[ERROR]') || line.includes('[FATAL') ? 'text-rose-400 font-bold bg-rose-500/10 px-2 py-0.5 rounded' :
                  line.includes('[STEP') || line.includes('[SYSTEM') ? 'text-amber-400 font-bold' :
                  line.includes('[EXEC]') ? 'text-cyan-400' : 'text-zinc-300'
                }
              >
                {line}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
}
