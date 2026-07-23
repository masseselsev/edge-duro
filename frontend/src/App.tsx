import React, { useState, useEffect, useRef } from 'react';
import { Flame, History, Settings as Gear, Terminal, Sun, Moon, User, Loader2, BookOpen, ArrowDown, ArrowUp } from 'lucide-react';
import RecipesTab from './components/RecipesTab';
import BuildsTab from './components/BuildsTab';
import SettingsTab from './components/SettingsTab';
import LogsTab from './components/LogsTab';
import Login from './components/Login';
import ProfileModal from './components/ProfileModal';
import LanguageSelector from './components/LanguageSelector';
import MainFooter from './components/MainFooter';
import BuildLogStream from './components/BuildLogStream';
import { TranslationProvider, useTranslation } from './context/TranslationContext';

type Tab = 'recipes' | 'builds' | 'settings' | 'logs';

function AppContent() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const saved = localStorage.getItem('activeTab') as Tab | null;
    const valid: Tab[] = ['recipes', 'builds', 'settings', 'logs'];
    return saved && valid.includes(saved) ? saved : 'recipes';
  });

  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('theme');
    return (saved === 'light' || saved === 'dark') ? saved : 'dark';
  });

  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [appVersion, setAppVersion] = useState('0.1.0');
  const [settings, setSettings] = useState<any>(null);
  const [appReady, setAppReady] = useState(false);
  const [healthWarnings, setHealthWarnings] = useState<any[]>([]);

  const [showProfileModal, setShowProfileModal] = useState(false);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const profileDropdownRef = useRef<HTMLDivElement>(null);

  const [activeStreamBuildId, setActiveStreamBuildId] = useState<string | null>(null);
  const [activeStreamRecipeName, setActiveStreamRecipeName] = useState<string>('');

  const [metrics, setMetrics] = useState<{ cpu_usage: number; ram_usage: number } | null>(null);

  useEffect(() => {
    localStorage.setItem('activeTab', activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (theme === 'light') {
      document.documentElement.classList.add('light');
    } else {
      document.documentElement.classList.remove('light');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Click outside to close profile dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (profileDropdownRef.current && !profileDropdownRef.current.contains(event.target as Node)) {
        setProfileDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Poll metrics
  useEffect(() => {
    if (!isAuthenticated) return;
    const fetchMetrics = async () => {
      try {
        const res = await fetch('/api/system/metrics');
        if (res.ok) {
          const data = await res.json();
          setMetrics(data);
        }
      } catch (err) {
        console.error('Metrics fetch error:', err);
      }
    };
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 3000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  // Auth check and initial metadata loading
  useEffect(() => {
    fetch('/api/auth/me')
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error('Not authenticated');
      })
      .then((user) => {
        setCurrentUser(user);
        setIsAuthenticated(true);
      })
      .catch(() => {
        setIsAuthenticated(false);
      })
      .finally(() => {
        setAppReady(true);
      });

    fetch('/api/version')
      .then((res) => res.json())
      .then((data) => {
        if (data && data.version) setAppVersion(data.version);
      })
      .catch((err) => console.error(err));

    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => {
        if (data && data.warnings) setHealthWarnings(data.warnings);
      })
      .catch((err) => console.error(err));
  }, []);

  const handleLoginSuccess = (user: any) => {
    setCurrentUser(user);
    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (err) {
      console.error(err);
    } finally {
      setIsAuthenticated(false);
      setCurrentUser(null);
      setProfileDropdownOpen(false);
    }
  };

  const handleBuildTriggered = (buildId: string, recipeName: string) => {
    setActiveStreamBuildId(buildId);
    setActiveStreamRecipeName(recipeName);
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'builds':
        return <BuildsTab />;
      case 'settings':
        return <SettingsTab onSettingsUpdated={setSettings} />;
      case 'logs':
        return <LogsTab />;
      case 'recipes':
      default:
        return <RecipesTab onBuildTriggered={handleBuildTriggered} />;
    }
  };

  if (!appReady) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950">
        <div className="flex flex-col items-center gap-4">
          <div className="p-3 bg-amber-500/15 border border-amber-500/30 rounded-2xl">
            <Flame className="w-8 h-8 text-amber-400 animate-pulse" />
          </div>
          <div className="flex items-center gap-2 text-xs font-semibold text-zinc-400">
            <Loader2 size={14} className="animate-spin text-amber-400" />
            <span>{t('loadingInitializing')}</span>
          </div>
        </div>
      </div>
    );
  }

  if (isAuthenticated === false) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-full flex flex-col font-sans pb-16">
      {/* Global Header matching Edge-B.R.O. exact compact scale */}
      <header className="bg-zinc-900/80 backdrop-blur-md border-b border-zinc-800/80 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-2.5 space-y-2.5">
          {/* Row 1: Logo/Title | Server Metrics | Actions */}
          <div className="flex flex-col md:flex-row items-center justify-between gap-3">
            {/* Left: Brand Identity */}
            <div className="flex-1 flex items-center gap-2.5 justify-center md:justify-start">
              <div className="relative p-1.5 bg-amber-500/15 border border-amber-500/30 rounded-lg shadow-lg flex items-center justify-center w-9 h-9">
                <Flame className="w-5 h-5 text-amber-400 filter drop-shadow-[0_0_4px_rgba(245,158,11,0.6)]" />
                <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-emerald-500 rounded-full animate-ping"></span>
                <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
              </div>
              <div>
                <h1 className="text-sm font-bold text-zinc-50 tracking-tight leading-none flex items-center gap-1.5">
                  <span className="bg-amber-500/10 text-amber-300 border border-amber-500/20 px-2 py-0.5 rounded font-mono font-bold text-[11px] uppercase tracking-wider">
                    {t('appName')}
                  </span>
                  <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-bold">
                    {appVersion}
                  </span>
                </h1>
                <p className="text-[9px] text-zinc-500 font-semibold mt-1 uppercase tracking-wider">
                  {t('appDescription')}
                </p>
              </div>
            </div>

            {/* Center: Server Metrics Widget */}
            {metrics && (
              <div className="flex-shrink-0 flex items-center gap-2.5 bg-zinc-950/40 border border-zinc-800/60 rounded-xl px-2.5 py-1 shadow-inner">
                <div className="flex items-center gap-1" title="CPU Utilization">
                  <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold font-mono">CPU</span>
                  <span className="text-[10px] font-mono font-semibold text-emerald-400">
                    {metrics.cpu_usage.toFixed(0)}%
                  </span>
                </div>
                <div className="w-px h-2.5 bg-zinc-800" />
                
                <div className="flex items-center gap-1" title="RAM Utilization">
                  <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold font-mono">RAM</span>
                  <span className="text-[10px] font-mono font-semibold text-emerald-400">
                    {metrics.ram_usage.toFixed(0)}%
                  </span>
                </div>
                <div className="w-px h-2.5 bg-zinc-800" />
                
                <div className="flex items-center gap-1">
                  <ArrowDown size={11} className="text-zinc-600" />
                  <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold font-mono">RX</span>
                  <span className="text-[10px] font-mono font-semibold text-emerald-400">0 B/s</span>
                  <span className="text-[8.5px] font-mono text-emerald-400">(0.0%)</span>
                </div>
                <div className="w-px h-2.5 bg-zinc-800" />
                
                <div className="flex items-center gap-1">
                  <ArrowUp size={11} className="text-zinc-600" />
                  <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold font-mono">TX</span>
                  <span className="text-[10px] font-mono font-semibold text-emerald-400">0 B/s</span>
                  <span className="text-[8.5px] font-mono text-emerald-400">(0.0%)</span>
                </div>
              </div>
            )}

            {/* Right: Actions + User Profile Dropdown */}
            <div className="flex-1 flex flex-wrap items-center justify-center md:justify-end gap-2">
              {currentUser && (
                <div className="relative" ref={profileDropdownRef}>
                  <button
                    onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-950 hover:bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-300 font-bold transition-all cursor-pointer outline-none"
                  >
                    <User size={12} className="text-zinc-400" />
                    <span>{currentUser.name || currentUser.username}</span>
                    <svg className={`w-2.5 h-2.5 text-zinc-500 transition-transform duration-200 ${profileDropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {profileDropdownOpen && (
                    <div className="absolute right-0 mt-1.5 w-40 rounded-lg bg-zinc-900 border border-zinc-800 shadow-2xl p-1 z-50 origin-top-right animate-dropdown-in">
                      <button
                        onClick={() => {
                          setProfileDropdownOpen(false);
                          setShowProfileModal(true);
                        }}
                        className="w-full text-left px-2.5 py-1.5 text-[11px] font-semibold rounded-md text-zinc-300 hover:text-zinc-50 hover:bg-zinc-800 transition-colors cursor-pointer"
                      >
                        {t('editProfile') || 'Edit Profile'}
                      </button>
                      <button
                        onClick={handleLogout}
                        className="w-full text-left px-2.5 py-1.5 text-[11px] font-semibold rounded-md text-rose-400 hover:bg-rose-950/20 transition-colors border-t border-zinc-800 mt-1 pt-1.5 cursor-pointer"
                      >
                        {t('logout')}
                      </button>
                    </div>
                  )}
                </div>
              )}

              <LanguageSelector />

              <button
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                className="p-1 bg-zinc-950 hover:bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-400 hover:text-zinc-200 transition-all cursor-pointer flex items-center justify-center w-7 h-7"
                title="Toggle Theme"
              >
                {theme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
              </button>
            </div>
          </div>

          {/* Row 2: Full Width Dark Pill Navigation Bar */}
          <div className="border-t border-zinc-800/60 pt-1.5 flex justify-center w-full">
            <nav className="w-full flex flex-wrap items-center justify-center gap-1 bg-zinc-950 p-1 rounded-xl border border-zinc-800/60">
              <button
                onClick={() => setActiveTab('recipes')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                  activeTab === 'recipes'
                    ? 'bg-zinc-900 text-zinc-100 shadow-sm border border-zinc-800'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <BookOpen size={13} className="text-amber-400" />
                <span>{t('tabRecipes')}</span>
              </button>
              <button
                onClick={() => setActiveTab('builds')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                  activeTab === 'builds'
                    ? 'bg-zinc-900 text-zinc-100 shadow-sm border border-zinc-800'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <History size={13} className="text-amber-400" />
                <span>{t('tabBuilds')}</span>
              </button>
              <button
                onClick={() => setActiveTab('logs')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                  activeTab === 'logs'
                    ? 'bg-zinc-900 text-zinc-100 shadow-sm border border-zinc-800'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <Terminal size={13} className="text-amber-400" />
                <span>{t('tabLogs')}</span>
              </button>
              <button
                onClick={() => setActiveTab('settings')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                  activeTab === 'settings'
                    ? 'bg-zinc-900 text-zinc-100 shadow-sm border border-zinc-800'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <Gear size={13} className="text-amber-400" />
                <span>{t('tabSettings')}</span>
              </button>
            </nav>
          </div>
        </div>
      </header>

      {/* Tab Content */}
      <main className="flex-1">
        {renderTabContent()}
      </main>

      {/* Main Footer */}
      <MainFooter
        appVersion={appVersion}
        healthWarnings={healthWarnings}
        setActiveTab={setActiveTab}
      />

      {/* Profile Modal */}
      {showProfileModal && currentUser && (
        <ProfileModal
          currentUser={currentUser}
          onClose={() => setShowProfileModal(false)}
          onUpdateSuccess={(updatedUser: any) => setCurrentUser(updatedUser)}
        />
      )}

      {/* Build Log Overlay Stream Modal */}
      {activeStreamBuildId && (
        <BuildLogStream
          buildId={activeStreamBuildId}
          recipeName={activeStreamRecipeName}
          onClose={() => setActiveStreamBuildId(null)}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <TranslationProvider>
      <AppContent />
    </TranslationProvider>
  );
}
