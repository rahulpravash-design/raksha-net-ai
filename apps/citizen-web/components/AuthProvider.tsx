"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, type User } from "@raksha/api-client";

import { getApiClient, tokenStore } from "@/lib/api";

interface AuthState {
  user: User | null;
  /** True until the stored session has been checked against the backend. */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const api = getApiClient(() => {
    setUser(null);
    router.push("/login");
  });

  const loadUser = useCallback(async () => {
    if (!tokenStore.getAccessToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.me());
    } catch (error) {
      // An expired or revoked session is an ordinary state, not a failure worth
      // surfacing — the visitor simply sees the signed-out view.
      if (!(error instanceof ApiError)) throw error;
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    // The session token lives in browser storage, so this data cannot be
    // fetched in a server component — it has to be loaded on mount. The rule
    // guards against cascading synchronous renders; every setState here
    // happens after an awaited response, which is not that case.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadUser();
  }, [loadUser]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.login(email, password);
      setUser(tokens.user);
    },
    [api],
  );

  const signOut = useCallback(async () => {
    await api.logout();
    setUser(null);
    router.push("/");
  }, [api, router]);

  const value = useMemo<AuthState>(
    () => ({ user, loading, signIn, signOut, refreshUser: loadUser }),
    [user, loading, signIn, signOut, loadUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside an AuthProvider.");
  }
  return context;
}
