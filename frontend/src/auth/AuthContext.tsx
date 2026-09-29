import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import { getAuthStatus, logout as apiLogout, type AuthStatus } from '../api/auth';

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  email?: string;
  scopes?: string[];
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  isAuthenticated: false,
  isLoading: true,
  logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<AuthState, 'logout'>>({
    isAuthenticated: false,
    isLoading: true,
  });

  const checkStatus = useCallback(async () => {
    try {
      const status: AuthStatus = await getAuthStatus();
      setState({
        isAuthenticated: status.authenticated,
        isLoading: false,
        email: status.email,
        scopes: status.scopes,
      });
    } catch {
      setState({ isAuthenticated: false, isLoading: false });
    }
  }, []);

  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  const logout = useCallback(async () => {
    await apiLogout();
    setState({ isAuthenticated: false, isLoading: false });
    window.location.href = '/login';
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
