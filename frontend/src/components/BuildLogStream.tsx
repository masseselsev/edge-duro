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
  const [isAtBottom, setIsAtBottom] = useState<boolean>(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const isAutoScrollingRef = useRef<boolean>(false);

  const handleScroll = () => {
    if (isAutoScrollingRef.current) return;
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
      const atBottom = scrollHeight - (scrollTop + clientHeight) < 150;
      setIsAtBottom((prev) => (prev !== atBottom ? atBottom : prev));
    }
  };

  const displayLogs = React.useMemo(() => {
    if (logs.length === 0) return [];
    const isProgressLine = (str: string): boolean => {
      const clean = str.replace(/^\[.*?\]\s*/, '').trim();
      if (!clean) return false;
      return /repart-definitions|->.*?\d+(?:M|G|K|B)\/\d+|(?:^|\s)\d+%\s*$/i.test(clean) ||
             /\b\d+(?:\.\d+)?(?:M|G|K|B)\/\d+(?:\.\d+)?(?:M|G|K|B)\b/i.test(clean);
    };

    const result: string[] = [];
    for (const line of logs) {
      if (!line) continue;
      const bodyOnly = line.replace(/^\[.*?\]\s*/, '').trim();
      if (!bodyOnly) continue;

      if (result.length > 0 && isProgressLine(line) && isProgressLine(result[result.length - 1])) {
        result[result.length - 1] = line;
      } else {
        result.push(line);
      }
    }
    return result;
  }, [logs]);

  useEffect(() => {
    if (isAtBottom && logContainerRef.current) {
      isAutoScrollingRef.current = true;
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      requestAnimationFrame(() => {
        isAutoScrollingRef.current = false;
      });
    }
  }, [displayLogs, isAtBottom]);

  const scrollToBottom = () => {
    setIsAtBottom(true);
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  };

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

  const fetchBuildStatus = (updateLogs: boolean = false) => {
    fetch(`/api/builds/${buildId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.log_output && updateLogs) {
          setLogs(data.log_output.split('\n').filter((l: string) => l.length > 0));
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
    fetchBuildStatus(true);

    const pollInterval = setInterval(() => {
      fetchBuildStatus(false);
    }, 3000);

    const eventSource = new EventSource(`/api/builds/${buildId}/stream`);

    eventSource.addEventListener('log', (event: MessageEvent) => {
      setLogs((prev) => [...prev, event.data]);
      if (event.data.includes('[ISO SUCCESS]')) {
        setHasIso(true);
      }
      if (event.data.includes('[SYSTEM] Build and ISO generation completed') || event.data.includes('Build completed successfully')) {
        fetchBuildStatus(false);
      }
    });

    eventSource.onerror = (err) => {
      console.warn("SSE connection error; native EventSource will attempt auto-reconnect.");
    };

    return () => {
      clearInterval(pollInterval);
      eventSource.close();
    };
  }, [buildId]);

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/85 animate-fade-in">
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
            {hasRaw && (
              <a
                href={`/api/builds/${buildId}/download?format=raw_xz`}
                className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 rounded-lg text-xs font-bold transition-colors flex items-center gap-1"
                title="Download compressed RAW.XZ image"
              >
                <Download size={13} />
                <span>RAW.XZ</span>
              </a>
            )}
            {hasIso && (
              <a
                href={`/api/builds/${buildId}/download?format=iso`}
                className="px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 text-amber-400 border border-zinc-800 rounded-lg text-xs font-bold transition-colors flex items-center gap-1"
                title="Download bootable ISO image"
              >
                <Disc size={13} />
                <span>ISO</span>
              </a>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Monospace Log Viewer */}
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          className="relative flex-1 p-5 overflow-y-auto font-mono text-xs text-zinc-300 space-y-1 bg-zinc-950 leading-relaxed"
        >
          {displayLogs.length === 0 ? (
            <div className="text-zinc-600 italic">Waiting for live build output stream...</div>
          ) : (
            displayLogs.map((line, i) => (
              <div
                key={i}
                style={{ contentVisibility: 'auto', containIntrinsicSize: '0 20px' }}
                className={
                  line.includes('[ERROR]') || line.includes('[FATAL') ? 'text-rose-400 font-bold bg-rose-500/10 px-2 py-0.5 rounded' :
                  line.includes('[STEP') || line.includes('[SYSTEM') || line.includes('[ISO SUCCESS]') ? 'text-amber-400 font-bold' :
                  line.includes('[EXEC]') || line.includes('[ISO EXEC]') ? 'text-cyan-400' : 'text-zinc-300'
                }
              >
                {line}
              </div>
            ))
          )}
          <div ref={logEndRef} />

          {/* Floating Jump to Bottom Button */}
          {!isAtBottom && (
            <button
              onClick={scrollToBottom}
              className="sticky bottom-4 right-4 ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500 text-zinc-950 font-sans font-bold text-xs shadow-lg hover:bg-amber-400 transition-all cursor-pointer z-10"
            >
              <ArrowDown size={14} />
              <span>Scroll to Bottom</span>
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
