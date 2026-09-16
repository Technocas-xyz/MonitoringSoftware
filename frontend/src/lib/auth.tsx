"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, clearTokens, getToken, setTokens } from "./api";
import type { Me, TokenPair } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (organization_slug: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  has: (perm: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      const data = await api<Me>("/auth/me");
      setMe(data);
    } catch {
      clearTokens();
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const login = useCallback(
    async (organization_slug: string, email: string, password: string) => {
      const tokens = await api<TokenPair>("/auth/login", {
        method: "POST",
        auth: false,
        body: { organization_slug, email, password },
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      const data = await api<Me>("/auth/me");
      setMe(data);
    },
    []
  );

  const logout = useCallback(() => {
    clearTokens();
    setMe(null);
    if (typeof window !== "undefined") window.location.href = "/login";
  }, []);

  const has = useCallback((perm: string) => !!me?.permissions.includes(perm), [me]);

  return (
    <AuthContext.Provider value={{ me, loading, login, logout, has }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
