import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  login as apiLogin,
  logout as apiLogout,
  type AuthUser,
  type OtpChallenge,
  isOtpChallenge,
} from '../api/auth';
import { IdleWarning, useIdleLogout } from './idle';

// Auth is session based on the server, but the SPA still needs to remember
// "am I logged in" across reloads. The session cookie is HttpOnly and not
// readable from JS, so we persist a lightweight copy of the user object in
// localStorage purely as a UI hint. If the cookie has actually expired, the
// next protected API call will 401 and the UI will bounce back to login.

const STORAGE_KEY = 'hmdm.admin.user';

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  /** Resolves to the user, or to an OtpChallenge when this computer still needs the emailed code. */
  signIn: (username: string, password: string, otp?: string) => Promise<AuthUser | OtpChallenge>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function loadStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(loadStoredUser);

  const signIn = useCallback(async (username: string, password: string, otp?: string) => {
    const u = await apiLogin(username, password, otp);
    if (isOtpChallenge(u)) return u;
    setUser(u);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(u));
    } catch {
      /* storage may be unavailable; non-fatal */
    }
    return u;
  }, []);

  const signOut = useCallback(async () => {
    await apiLogout();
    setUser(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* non-fatal */
    }
  }, []);

  // Signed in and idle too long: end the session. The route guard then returns the person to the sign-in page.
  const idleLeft = useIdleLogout(user !== null, () => { void signOut(); });

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: user !== null, signIn, signOut }),
    [user, signIn, signOut],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      {user !== null && idleLeft !== null ? <IdleWarning seconds={idleLeft} /> : null}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
