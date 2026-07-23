import React, { useState, useEffect } from 'react';
import { Flame, History, Settings as Gear, Terminal, Sun, Moon, User, Loader2, BookOpen } from 'lucide-react';
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
  const { t, language } = useTranslation();
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
  const [activeStreamBuildId, setActiveStreamBuildId] = useState<string | null>(null);
  const [activeStreamRecipeName, setActiveStreamRecipeName] = useState<string>('');

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
      {/* Global Header */}
      <header className="bg-zinc-900/80 backdrop-blur-md border-b border-zinc-800/80 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-3 space-y-3">
          <div className="flex items-center justify-between gap-4">
            {/* Brand Logo */}
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-500/15 border border-amber-500/30 rounded-lg shadow-lg flex items-center justify-center w-10 h-10">
                <Flame className="w-6 h-6 text-amber-400" />
              </div>
              <div>
                <h1 className="text-base font-bold text-zinc-50 tracking-tight leading-none flex items-center gap-2">
                  <span className="bg-amber-500/10 text-amber-300 border border-amber-500/20 px-2 py-0.5 rounded font-mono font-bold text-xs uppercase tracking-wider">
                    {t('appName')}
                  </span>
                  <span className="text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30 px-1.5 py-0.5 rounded font-mono font-bold">
                    {appVersion}
                  </span>
                </h1>
                <p className="text-[9px] text-zinc-500 font-semibold mt-1 uppercase tracking-wider">
                  {t('appDescription')}
                </p>
              </div>
            </div>

            {/* Actions & Controls */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                className="p-2 rounded-lg bg-zinc-950 hover:bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
                title="Toggle Theme"
              >
                {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              </button>

              <LanguageSelector />

              {currentUser && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowProfileModal(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-950 hover:bg-zinc-900 border border-zinc-800 text-xs text-zinc-300 font-bold transition-all cursor-pointer"
                  >
                    <User size={13} className="text-amber-400" />
                    <span>{currentUser.name || currentUser.username}</span>
                  </button>
                  <button
                    onClick={handleLogout}
                    className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-xs text-rose-400 font-bold transition-all cursor-pointer"
                  >
                    {t('logout')}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Navigation Bar */}
          <div className="pt-2 border-t border-zinc-800/60">
            <nav className="flex items-center gap-2">
              <button
                onClick={() => setActiveTab('recipes')}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'recipes'
                    ? 'bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <BookOpen size={14} className="text-amber-400" />
                <span>{t('tabRecipes')}</span>
              </button>
              <button
                onClick={() => setActiveTab('builds')}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'builds'
                    ? 'bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <History size={14} className="text-amber-400" />
                <span>{t('tabBuilds')}</span>
              </button>
              <button
                onClick={() => setActiveTab('logs')}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'logs'
                    ? 'bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <Terminal size={14} className="text-amber-400" />
                <span>{t('tabLogs')}</span>
              </button>
              <button
                onClick={() => setActiveTab('settings')}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'settings'
                    ? 'bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <Gear size={14} className="text-amber-400" />
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
      {showProfileModal && (
        <ProfileModal
          currentUser={currentUser}
          onClose={() => setShowProfileModal(false)}
          onUpdateSuccess={(updated) => setCurrentUser(updated)}
        />
      )}

      {/* SSE Log Stream Modal */}
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
