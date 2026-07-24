import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Terminal, X, Circle, Download, CheckCircle2, Disc, ArrowDown, ArrowUp } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface BuildLogStreamProps {
  buildId: string;
  recipeName?: string;
  onClose: () => void;
}

interface SystemMetrics {
  cpu_usage: number;
  ram_usage: number;
  rx_speed: number;
  tx_speed: number;
  rx_percent: number;
  tx_percent: number;
}

const formatSpeed = (bytesPerSec: number): string => {
  if (!bytesPerSec || bytesPerSec < 1024) return `${(bytesPerSec || 0).toFixed(0)} B/s`;
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
  if (bytesPerSec < 1024 * 1024 * 1024) return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`;
  return `${(bytesPerSec / (1024 * 1024 * 1024)).toFixed(1)} GB/s`;
};

export default function BuildLogStream({ buildId, recipeName, onClose }: BuildLogStreamProps) {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<string[]>([]);
  const [status, setStatus] = useState<string>('PENDING');
  const [hasIso, setHasIso] = useState<boolean>(false);
  const [hasRaw, setHasRaw] = useState<boolean>(false);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch('/api/system/metrics');
        if (res.ok) {
          const data = await res.json();
          setMetrics(data);
        }
      } catch (err) {
        console.error(err);
      }
    };
    fetchMetrics();
    const mInterval = setInterval(fetchMetrics, 3000);
    return () => clearInterval(mInterval);
  }, []);

  const fetchBuildStatus = () => {
    fetch(`/api/builds/${buildId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.log_output) {
          setLogs(data.log_output.split('\n'));
        }
        if (data.status) {
          setStatus(data.status);
        }
        if (data.artifact_path) {
          setHasRaw(true);
        }
        if (data.iso_artifact_path || (data.log_output && data.log_output.includes('[ISO SUCCESS]'))) {
          setHasIso(true);
        }
      })
      .catch((err) => console.error(err));
  };

  useEffect(() => {
    fetchBuildStatus();

    // Polling while build is running or pending
    const pollInterval = setInterval(() => {
      fetchBuildStatus();
    }, 1500);

    // Connect SSE stream for realtime line appends
    const eventSource = new EventSource(`/api/builds/${buildId}/stream`);

    eventSource.addEventListener('log', (event: MessageEvent) => {
      setLogs((prev) => [...prev, event.data]);
      if (event.data.includes('[ISO SUCCESS]')) {
        setHasIso(true);
      }
      if (event.data.includes('[SYSTEM] Build and ISO generation completed') || event.data.includes('Build completed successfully')) {
        fetchBuildStatus();
      }
    });

    eventSource.onerror = (err) => {
      eventSource.close();
    };

    return () => {
      clearInterval(pollInterval);
      eventSource.close();
    };
  }, [buildId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
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
                <span className={`flex items-center gap-1.5 text-[10px] font-mono px-2.5 py-0.5 rounded-full border ${
                  status === 'SUCCESS' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' :
                  status === 'RUNNING' ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' :
                  status === 'PENDING' ? 'bg-zinc-800 text-zinc-300 border-zinc-700' :
                  'bg-rose-500/10 text-rose-400 border-rose-500/30'
                }`}>
                  {status === 'SUCCESS' ? (
                    <CheckCircle2 size={10} className="text-emerald-400" />
                  ) : (
                    <Circle
                      size={8}
                      className={
                        status === 'RUNNING' || status === 'PENDING' ? 'text-amber-400 fill-amber-400 animate-pulse' :
                        'text-rose-400 fill-rose-400'
                      }
                    />
                  )}
                  <span className="font-bold uppercase tracking-wider">{status}</span>
                </span>
              </div>
              <p className="text-[10px] text-zinc-500 font-mono">ID: {buildId}</p>
            </div>
          </div>

          {/* Server Metrics Badge in Console Header */}
          {metrics && (
            <div className="hidden sm:flex items-center gap-2.5 bg-zinc-950/60 border border-zinc-800/80 rounded-xl px-2.5 py-1 shadow-inner text-[10px] font-mono">
              <div className="flex items-center gap-1" title="CPU Utilization">
                <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold">CPU</span>
                <span className="font-semibold text-emerald-400">{metrics.cpu_usage.toFixed(0)}%</span>
              </div>
              <div className="w-px h-2.5 bg-zinc-800" />
              <div className="flex items-center gap-1" title="RAM Utilization">
                <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold">RAM</span>
                <span className="font-semibold text-emerald-400">{metrics.ram_usage.toFixed(0)}%</span>
              </div>
              <div className="w-px h-2.5 bg-zinc-800" />
              <div className="flex items-center gap-1" title="Download Speed">
                <ArrowDown size={11} className={metrics.rx_speed > 1024 ? "text-emerald-400 animate-pulse" : "text-zinc-600"} />
                <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold">RX</span>
                <span className="font-semibold text-emerald-400">{formatSpeed(metrics.rx_speed)}</span>
                <span className="text-[8.5px] text-emerald-400">({metrics.rx_percent.toFixed(1)}%)</span>
              </div>
              <div className="w-px h-2.5 bg-zinc-800" />
              <div className="flex items-center gap-1" title="Upload Speed">
                <ArrowUp size={11} className={metrics.tx_speed > 1024 ? "text-emerald-400 animate-pulse" : "text-zinc-600"} />
                <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold">TX</span>
                <span className="font-semibold text-emerald-400">{formatSpeed(metrics.tx_speed)}</span>
                <span className="text-[8.5px] text-emerald-400">({metrics.tx_percent.toFixed(1)}%)</span>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            {/* Download Buttons for available formats */}
            {(hasRaw || status === 'SUCCESS') && (
              <a
                href={`/api/builds/${buildId}/download?format=raw_xz`}
                className="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-zinc-950 rounded-lg text-xs font-bold transition-all shadow-md flex items-center gap-1.5"
                title="Download compressed RAW.XZ image"
              >
                <Download size={13} />
                <span>RAW.XZ</span>
              </a>
            )}

            {(hasIso || status === 'SUCCESS') && (
              <a
                href={`/api/builds/${buildId}/download?format=iso`}
                className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg text-xs font-bold text-amber-400 transition-colors flex items-center gap-1.5"
                title="Download bootable ISO image"
              >
                <Disc size={13} />
                <span>ISO</span>
              </a>
            )}

            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer ml-2"
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
            (() => {
              const isProgressLine = (str: string): boolean => {
                const clean = str.replace(/^\[.*?\]\s*/, '').trim();
                if (!clean) return false;
                return /repart-definitions|->.*?\d+(?:M|G|K|B)\/\d+|(?:^|\s)\d+%\s*$/i.test(clean) ||
                       /\b\d+(?:\.\d+)?(?:M|G|K|B)\/\d+(?:\.\d+)?(?:M|G|K|B)\b/i.test(clean);
              };

              const displayLogs: string[] = [];
              for (const line of logs) {
                if (!line) continue;
                const bodyOnly = line.replace(/^\[.*?\]\s*/, '').trim();
                if (!bodyOnly) continue; // Skip blank timestamp lines

                if (displayLogs.length > 0 && isProgressLine(line) && isProgressLine(displayLogs[displayLogs.length - 1])) {
                  displayLogs[displayLogs.length - 1] = line;
                } else {
                  displayLogs.push(line);
                }
              }

              return displayLogs.map((line, i) => (
                <div
                  key={i}
                  className={
                    line.includes('[ERROR]') || line.includes('[FATAL') ? 'text-rose-400 font-bold bg-rose-500/10 px-2 py-0.5 rounded' :
                    line.includes('[STEP') || line.includes('[SYSTEM') || line.includes('[ISO SUCCESS]') ? 'text-amber-400 font-bold' :
                    line.includes('[EXEC]') || line.includes('[ISO EXEC]') ? 'text-cyan-400' : 'text-zinc-300'
                  }
                >
                  {line}
                </div>
              ));
            })()
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>,
    document.body
  );
}
