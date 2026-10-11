import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Session = {
  userId: string;
  userName: string;
  roles: string[];
  csrf: string;
};

const STORAGE_KEY = "emaw.console.session.v2";

type AuthCtx = {
  session: Session | null;
  ready: boolean;
  login: (session: Session) => void;
  logout: () => void;
  setSession: (session: Session | null) => void;
};

const Ctx = createContext<AuthCtx | null>(null);

function load(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (!parsed?.userId || !parsed?.csrf) return null;
    return parsed;
  } catch {
    return null;
  }
}

function persist(session: Session | null) {
  if (!session) {
    sessionStorage.removeItem(STORAGE_KEY);
    return;
  }
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(() => load());
  const [ready, setReady] = useState(false);

  const setSession = useCallback((next: Session | null) => {
    persist(next);
    setSessionState(next);
  }, []);

  const login = useCallback(
    (next: Session) => {
      setSession(next);
    },
    [setSession],
  );

  const logout = useCallback(() => {
    setSession(null);
  }, [setSession]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/internal/auth/me", { credentials: "include" });
        if (!res.ok) {
          if (!cancelled) setSession(null);
          return;
        }
        const body = (await res.json()) as {
          user_id: number;
          name: string;
          roles: string[];
          csrf: string | null;
          auth?: string;
        };
        if (body.auth === "service" || !body.csrf) {
          // Cookie session required for the SPA; ignore service-shaped /me.
          return;
        }
        if (!cancelled) {
          setSession({
            userId: String(body.user_id),
            userName: body.name,
            roles: body.roles || [],
            csrf: body.csrf,
          });
        }
      } catch {
        /* keep cached session until first API call fails */
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setSession]);

  const value = useMemo(
    () => ({ session, ready, login, logout, setSession }),
    [session, ready, login, logout, setSession],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
