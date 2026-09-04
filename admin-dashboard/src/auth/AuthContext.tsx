import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api, ApiError } from '@/api/client';
import type { Session, User } from '@/types';

const SESSION_KEY = 'lg_session_v1';

interface AuthState {
  user: User | null;
  token: string | null;
  status: 'loading' | 'authenticated' | 'anonymous';
  login: (email: string, password: string, remember: boolean) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function readStoredSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session?.token || !session?.user) return null;
    if (session.expiresAt && +new Date(session.expiresAt) < Date.now()) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => readStoredSession()?.user ?? null);
  const [token, setToken] = useState<string | null>(() => readStoredSession()?.token ?? null);
  const [status, setStatus] = useState<AuthState['status']>(() =>
    readStoredSession() ? 'authenticated' : 'anonymous',
  );

  /* Revalidate the persisted session against the API on boot. */
  useEffect(() => {
    let cancelled = false;
    const stored = readStoredSession();
    if (!stored) {
      setStatus('anonymous');
      return;
    }
    setStatus('loading');
    api.auth
      .me(stored.token)
      .then((fresh) => {
        if (cancelled) return;
        setUser(fresh);
        setToken(stored.token);
        setStatus('authenticated');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          localStorage.removeItem(SESSION_KEY);
        }
        setUser(null);
        setToken(null);
        setStatus('anonymous');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string, remember: boolean) => {
    const session = await api.auth.login({ email, password, remember });
    if (remember) {
      localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } else {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    }
    setUser(session.user);
    setToken(session.token);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } catch {
      /* logging out should never be blocked by a network blip */
    }
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    setUser(null);
    setToken(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, token, status, login, logout }),
    [user, token, status, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>.');
  return ctx;
}
