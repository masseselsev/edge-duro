import React, { useState } from 'react';
import { Flame, Lock, User, Loader2, ShieldAlert } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

interface LoginProps {
  onLoginSuccess: (user: any) => void;
}

export default function Login({ onLoginSuccess }: LoginProps) {
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      let data: any = {};
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      }

      if (!res.ok) {
        throw new Error(data.detail || `Server returned HTTP ${res.status}. Please check backend logs.`);
      }

      onLoginSuccess(data.user);
    } catch (err: any) {
      setError(err.message || t('loginError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-md p-8 bg-zinc-900/90 border border-zinc-800 rounded-3xl shadow-2xl space-y-6 animate-modal-in">
        
        {/* Header Identity */}
        <div className="flex flex-col items-center text-center space-y-3">
          <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl shadow-xl flex items-center justify-center w-14 h-14">
            <Flame className="w-8 h-8 text-amber-400 filter drop-shadow-[0_0_6px_rgba(245,158,11,0.6)]" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-zinc-50 tracking-tight">{t('loginTitle')}</h2>
            <p className="text-xs text-amber-400/80 font-semibold uppercase tracking-wider mt-1 font-mono">
              Edge-D.U.R.O.
            </p>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="flex items-start gap-2.5 p-3.5 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl text-xs font-semibold animate-fade-in leading-relaxed">
            <ShieldAlert size={16} className="shrink-0 text-rose-400 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="username" className="block text-xs font-bold text-zinc-400 uppercase tracking-wider pl-1">{t('loginUsername')}</label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-500">
                <User size={16} />
              </span>
              <input
                type="text"
                id="username"
                name="username"
                autoComplete="username"
                required
                disabled={loading}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-zinc-950/80 border border-zinc-800 hover:border-zinc-700 focus:border-amber-500 rounded-xl text-zinc-100 text-sm focus:outline-none transition-all duration-200"
                placeholder="e.g. admin"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="block text-xs font-bold text-zinc-400 uppercase tracking-wider pl-1">{t('loginPassword')}</label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-500">
                <Lock size={16} />
              </span>
              <input
                type="password"
                id="password"
                name="password"
                autoComplete="current-password"
                required
                disabled={loading}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-zinc-950/80 border border-zinc-800 hover:border-zinc-700 focus:border-amber-500 rounded-xl text-zinc-100 text-sm focus:outline-none transition-all duration-200"
                placeholder="••••••••"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-zinc-950 rounded-xl font-bold text-sm tracking-wide shadow-lg shadow-amber-500/10 hover:shadow-amber-500/20 transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin text-zinc-950" />
            ) : (
              t('loginSubmit')
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
