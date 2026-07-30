import React, { useState } from 'react';
import { KeyRound, Plus, Trash2, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import FieldLabel from './FieldLabel';

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

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  // DEFAULT_USER_GROUPS already includes "sudo", so a new user is admin by
  // default, matching the previous simple-cdd preseed's "user" account.
  const [newIsSudo, setNewIsSudo] = useState(true);

  const handleAddUser = (e: React.FormEvent) => {
    e.preventDefault();
    const username = newUsername.trim();
    if (!username || !NAME_RE.test(username)) return;
    if (users.some((u) => u.username === username)) return;

    const groups = newIsSudo
      ? [...DEFAULT_USER_GROUPS]
      : DEFAULT_USER_GROUPS.filter((g) => g !== 'sudo');

    onUsersChange([...users, { username, password: newPassword, groups, shell: '/bin/bash' }]);
    setNewUsername('');
    setNewPassword('');
    setNewIsSudo(true);
  };

  const handleUpdateUser = (index: number, field: keyof UserAccount, value: any) => {
    onUsersChange(users.map((u, i) => (i === index ? { ...u, [field]: value } : u)));
  };

  const handleToggleSudo = (index: number, checked: boolean) => {
    const groups = users[index].groups || [];
    const next = checked ? Array.from(new Set([...groups, 'sudo'])) : groups.filter((g) => g !== 'sudo');
    handleUpdateUser(index, 'groups', next);
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
        <FieldLabel
          hint={
            t('rootPasswordHint') ||
            'Plaintext, or a pre-hashed crypt(3) string starting with $6$/$5$/etc. Installed with chpasswd during the build, so the image never stores a plaintext password. Leave empty to keep root locked (SSH keys / console autologin only).'
          }
        >
          {t('rootPassword') || 'Root Password'}
        </FieldLabel>
        <input
          type="text"
          value={rootPassword}
          onChange={(e) => onRootPasswordChange(e.target.value)}
          placeholder={t('rootPasswordPlaceholder') || 'Leave empty to keep root locked'}
          autoComplete="off"
          spellCheck={false}
          className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-xl text-zinc-100 text-xs font-mono focus:outline-none"
        />
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
                <label
                  title={
                    t('usernameHint') ||
                    'Lowercase letters, digits, underscore or hyphen; must start with a letter or underscore.'
                  }
                  className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
                >
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
                <label
                  title={
                    t('userPasswordHint') ||
                    'Plaintext or a pre-hashed $6$... string, same rules as the root password above.'
                  }
                  className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
                >
                  {t('password') || 'Password'}
                </label>
                <input
                  type="text"
                  value={user.password || ''}
                  onChange={(e) => handleUpdateUser(index, 'password', e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                />
              </div>

              <div className="sm:col-span-3">
                <label
                  title={
                    t('userGroupsHint') ||
                    'Comma-separated, no spaces, e.g. sudo,video,plugdev. Groups that do not exist yet are created automatically.'
                  }
                  className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
                >
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

              <div className="sm:col-span-12">
                <label
                  title={
                    t('sudoCheckboxHint') ||
                    'Grants full root access via sudo (adds/removes the "sudo" group). The sudo package is always included in the build, so this checkbox is never inert.'
                  }
                  className="inline-flex items-center gap-2 cursor-pointer select-none"
                >
                  <input
                    type="checkbox"
                    checked={(user.groups || []).includes('sudo')}
                    onChange={(e) => handleToggleSudo(index, e.target.checked)}
                    className="w-4 h-4 rounded border-zinc-800 bg-zinc-950 text-emerald-500 focus:ring-emerald-500/20"
                  />
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-[11px] text-zinc-300 font-medium">
                    {t('addToSudo') || 'Add to sudo (admin access)'}
                  </span>
                </label>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add user */}
      <div className="p-3.5 rounded-xl bg-slate-900/40 border border-dashed border-slate-800">
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
          <div className="sm:col-span-4">
            <label
              title={
                t('usernameHint') ||
                'Lowercase letters, digits, underscore or hyphen; must start with a letter or underscore.'
              }
              className="block text-[10px] uppercase font-semibold text-slate-500 mb-1 cursor-help"
            >
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
              type="text"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="off"
              spellCheck={false}
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
          <div className="sm:col-span-12">
            <label
              title={
                t('sudoCheckboxHint') ||
                'Grants full root access via sudo (adds/removes the "sudo" group). The sudo package is always included in the build, so this checkbox is never inert.'
              }
              className="inline-flex items-center gap-2 cursor-pointer select-none"
            >
              <input
                type="checkbox"
                checked={newIsSudo}
                onChange={(e) => setNewIsSudo(e.target.checked)}
                className="w-4 h-4 rounded border-zinc-800 bg-zinc-950 text-emerald-500 focus:ring-emerald-500/20"
              />
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[11px] text-zinc-300 font-medium">
                {t('addToSudo') || 'Add to sudo (admin access)'}
              </span>
            </label>
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
