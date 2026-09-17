import { createContext, useCallback, useEffect, useState, type ReactNode } from "react";
import type { LoginCredentials, RegisterCredentials, User } from "../types/auth";
import { authApi, tokenStorage, onUnauthorized } from "../services/api";

export interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (credentials: RegisterCredentials) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(tokenStorage.get());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const handleUnauthorized = useCallback(() => {
    tokenStorage.clear();
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    onUnauthorized(handleUnauthorized);
    return () => {
      onUnauthorized(null);
    };
  }, [handleUnauthorized]);

  const refreshUser = useCallback(async () => {
    const currentToken = tokenStorage.get();
    if (!currentToken) {
      setUser(null);
      setToken(null);
      setIsLoading(false);
      return;
    }

    try {
      const profile = await authApi.getMe();
      setUser(profile);
      setToken(currentToken);
    } catch {
      // Token expired or invalid
      tokenStorage.clear();
      setUser(null);
      setToken(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);


  const login = async (credentials: LoginCredentials) => {
    const tokenRes = await authApi.login(credentials);
    tokenStorage.set(tokenRes.access_token);
    setToken(tokenRes.access_token);
    const profile = await authApi.getMe();
    setUser(profile);
  };

  const register = async (credentials: RegisterCredentials) => {
    await authApi.register(credentials);
    // Automatically log in after registration
    await login({
      email: credentials.email,
      password: credentials.password,
    });
  };

  const logout = () => {
    tokenStorage.clear();
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user && !!token,
        isLoading,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
