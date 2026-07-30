import React, { useState } from 'react';
import { KeyRound, Plus, Trash2, Eye, EyeOff, ShieldAlert } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';

export interface UserAccount {
  username: string;
  password?: string;
  groups: string[];
  shell: string;
}

interface CredentialsEditorProps {
  rootPassword: string;
  users: UserAccount[];
  onRootPasswordChange: (value: string) => void;
  onUsersChange: (users: UserAccount[]) => void;
}

// Matches the groups the previous simple-cdd preseed granted its "user" account.
export const DEFAULT_USER_GROUPS = ['sudo', 'plugdev', 'netdev', 'video'];

const SHELLS = ['/bin/bash', '/bin/sh', '/usr/sbin/nologin'];

// Mirrors the backend schema validator so invalid names are caught before save.
const NAME_RE = /^[a-z_][a-z0-9_-]*$/;

export default function CredentialsEditor({
  rootPassword,
  users,
  onRootPasswordChange,
  onUsersChange,
}: CredentialsEditorProps) {
  const { t } = useTranslation();

  const [showRoot, setShowRoot] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');

  const handleAddUser = (e: React.FormEvent) => {
    e.preventDefault();
    const username = newUsername.trim();
    if (!username || !NAME_RE.test(username)) return;
    if (users.some((u) => u.username === username)) return;

    onUsersChange([
      ...users,
      { username, password: newPassword, groups: [...DEFAULT_USER_GROUPS], shell: '/bin/bash' },
    ]);
    setNewUsername('');
    setNewPassword('');
  };

  const handleUpdateUser = (index: number, field: keyof UserAccount, value: any) => {
    onUsersChange(users.map((u, i) => (i === index ? { ...u, [field]: value } : u)));
  };

  const handleRemoveUser = (index: number) => {
    onUsersChange(users.filter((_, i) => i !== index));
  };

  const usernameInvalid = newUsername.length > 0 && !NAME_RE.test(newUsername);
  const usernameTaken = users.some((u) => u.username === newUsername.trim());

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
        <div className="flex items-center gap-2 font-semibold text-slate-200">
          <KeyRound className="w-5 h-5 text-sky-400" />
          <span>{t('credentials') || 'Credentials'}</span>
        </div>
        <p className="text-xs text-slate-400 mt-1">
          {t('credentialsSubtitle') ||
            'Set the root password and additional login accounts. Leave root empty to keep the account locked (SSH keys only).'}
        </p>
      </div>

      {/* Root password */}
      <div className="space-y-1.5">
        <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
          {t('rootPassword') || 'Root Password'}
        </label>
        <div className="relative">
          <input
            type={showRoot ? 'text' : 'password'}
            value={rootPassword}
            onChange={(e) => onRootPasswordChange(e.target.value)}
            placeholder={t('rootPasswordPlaceholder') || 'Leave empty to keep root locked'}
            autoComplete="new-password"
            className="w-full px-3 py-2 pr-10 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-xs font-mono focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setShowRoot(!showRoot)}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
            aria-label={showRoot ? 'Hide password' : 'Show password'}
          >
            {showRoot ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {!rootPassword && (
          <p className="flex items-start gap-1.5 text-[11px] text-amber-500/80">
            <ShieldAlert className="w-3.5 h-3.5 mt-px shrink-0" />
            <span>
              {t('rootLockedWarning') ||
                'Root stays locked: console autologin and SSH keys will be the only way in.'}
            </span>
          </p>
        )}
      </div>

      {/* Existing users */}
      {users.length > 0 && (
        <div className="space-y-3">
          {users.map((user, index) => (
            <div
              key={index}
              className="grid grid-cols-1 sm:grid-cols-12 gap-3 p-3.5 rounded-xl bg-slate-900/40 border border-slate-800/80 items-start hover:border-slate-700 transition-colors animate-modal-in"
            >
              <div className="sm:col-span-3">
                <label className="block text-[10px] uppercase font-semibold text-slate-500 mb-1">
                  {t('username') || 'Username'}
                </label>
                <input
                  type="text"
                  value={user.username}
                  onChange={(e) => handleUpdateUser(index, 'username', e.target.value)}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                />
              </div>

              <div className="sm:col-span-3">
                <label className="block text-[10px] uppercase font-semibold text-slate-500 mb-1">
                  {t('password') || 'Password'}
                </label>
                <input
                  type="password"
                  value={user.password || ''}
                  onChange={(e) => handleUpdateUser(index, 'password', e.target.value)}
                  autoComplete="new-password"
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                />
              </div>

              <div className="sm:col-span-3">
                <label className="block text-[10px] uppercase font-semibold text-slate-500 mb-1">
                  {t('userGroups') || 'Groups'}
                </label>
                <input
                  type="text"
                  value={(user.groups || []).join(',')}
                  onChange={(e) =>
                    handleUpdateUser(
                      index,
                      'groups',
                      e.target.value.split(',').map((g) => g.trim()).filter(Boolean)
                    )
                  }
                  placeholder="sudo,video"
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-[10px] uppercase font-semibold text-slate-500 mb-1">
                  {t('loginShell') || 'Shell'}
                </label>
                <select
                  value={user.shell || '/bin/bash'}
                  onChange={(e) => handleUpdateUser(index, 'shell', e.target.value)}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 cursor-pointer font-mono"
                >
                  {SHELLS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>

              <div className="sm:col-span-1 flex sm:justify-end sm:pt-5">
                <button
                  type="button"
                  onClick={() => handleRemoveUser(index)}
                  className="p-2 text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors cursor-pointer"
                  aria-label={`Remove ${user.username}`}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add user */}
      <div className="p-3.5 rounded-xl bg-slate-900/40 border border-dashed border-slate-800">
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
          <div className="sm:col-span-4">
            <label className="block text-[10px] uppercase font-semibold text-slate-500 mb-1">
              {t('username') || 'Username'}
            </label>
            <input
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="user"
              className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
            />
          </div>
          <div className="sm:col-span-5">
            <label className="block text-[10px] uppercase font-semibold text-slate-500 mb-1">
              {t('password') || 'Password'}
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
            />
          </div>
          <div className="sm:col-span-3">
            <button
              type="button"
              onClick={handleAddUser}
              disabled={!newUsername.trim() || usernameInvalid || usernameTaken}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-sky-400 hover:text-sky-300 bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{t('addUser') || 'Add User'}</span>
            </button>
          </div>
        </div>
        {(usernameInvalid || usernameTaken) && (
          <p className="mt-2 text-[11px] text-red-400">
            {usernameTaken
              ? t('usernameTaken') || 'That username is already defined.'
              : t('usernameInvalid') ||
                'Must start with a lowercase letter or underscore; only lowercase letters, digits, underscore and hyphen.'}
          </p>
        )}
      </div>
    </div>
  );
}
