import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

const KEY = 'aradhana.profile.v1';

export type Profile = {
  mobile: string;
  acceptedAt: string;
  status: 'IDENTIFIED_UNVERIFIED';
};

const ProfileContext = createContext<{
  profile: Profile | null;
  ready: boolean;
  accept: (mobile: string) => Promise<void>;
}>({ profile: null, ready: false, accept: async () => {} });

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (mounted && raw) setProfile(JSON.parse(raw) as Profile);
      })
      .catch(() => {})
      .finally(() => {
        if (mounted) setReady(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const accept = useCallback(async (mobile: string) => {
    const p: Profile = {
      mobile,
      acceptedAt: new Date().toISOString(),
      status: 'IDENTIFIED_UNVERIFIED',
    };
    await AsyncStorage.setItem(KEY, JSON.stringify(p));
    setProfile(p);
  }, []);

  return (
    <ProfileContext.Provider value={{ profile, ready, accept }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  return useContext(ProfileContext);
}
