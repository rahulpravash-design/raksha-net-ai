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

import { admissionRefusal } from "@/lib/admission";
import { getApiClient, tokenStore } from "@/lib/api";

interface AuthState {
  user: User | null;
  /** True until the stored session has been checked against the backend. */
  loading: boolean;
  signIn: (email: string, password: string, mfaCode?: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const api = getApiClient(
    () => {
      setUser(null);
      router.push("/login");
    },
    // Policy requires two-factor for this account: everything else is refused
    // until it is set up, so take the user straight to the place that does it.
    () => router.push("/account/security"),
    // An administrator-set password is still in force: it must be replaced first.
    () => router.push("/account/security"),
  );

  const loadUser = useCallback(async () => {
    if (!tokenStore.getAccessToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      // A restored session is admitted on the same terms as a fresh sign-in.
      setUser(admissionRefusal(me.role) ? null : me);
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
    async (email: string, password: string, mfaCode?: string) => {
      const tokens = await api.login(email, password, mfaCode);
      const refusal = admissionRefusal(tokens.user.role);
      if (refusal) {
        await api.logout();
        throw new ApiError(403, refusal);
      }
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
