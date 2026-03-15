import { createContext, useContext, useState, useCallback } from "react";
import type { ReactNode } from "react";
import { authApi, type LoginRequest } from "../api/client";

interface AuthContextValue {
  token: string | null;
  login: (data: LoginRequest) => Promise<string>;
  register: (data: LoginRequest) => Promise<string>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => sessionStorage.getItem("token"),
  );

  const login = useCallback(async (data: LoginRequest) => {
    const res = await authApi.login(data);
    const t = res.data.access_token;
    sessionStorage.setItem("token", t);
    setToken(t);
    return t;
  }, []);

  const register = useCallback(async (data: LoginRequest) => {
    const res = await authApi.register(data);
    const t = res.data.access_token;
    sessionStorage.setItem("token", t);
    setToken(t);
    return t;
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem("token");
    setToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
