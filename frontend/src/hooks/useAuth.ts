import { useState, useCallback } from "react";
import { authApi, type LoginRequest } from "../api/client";

export function useAuth() {
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

  return { token, login, register, logout };
}
