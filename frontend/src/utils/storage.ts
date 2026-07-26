export function getSavedLimit(pageKey: string, defaultLimit = 25): number {
  try {
    const username = localStorage.getItem('duro_username') || 'default';
    const val = localStorage.getItem(`duro_limit_${username}_${pageKey}`) || localStorage.getItem(`duro_limit_${pageKey}`);
    return val ? Number(val) : defaultLimit;
  } catch {
    return defaultLimit;
  }
}

export function saveLimit(pageKey: string, limit: number): void {
  try {
    const username = localStorage.getItem('duro_username') || 'default';
    localStorage.setItem(`duro_limit_${username}_${pageKey}`, String(limit));
    localStorage.setItem(`duro_limit_${pageKey}`, String(limit));
  } catch (err) {
    console.error('Failed to save page limit preference:', err);
  }
}
