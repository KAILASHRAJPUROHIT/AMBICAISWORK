import { DefaultTheme, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { Platform, StatusBar, View } from 'react-native';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import AppTabs from '@/components/app-tabs';
import { WishlistProvider } from '@/store/wishlist';
import { ProfileProvider, useProfile } from '@/store/profile';
import { CartProvider } from '@/store/cart';
import { LangProvider } from '@/store/lang';
import OnboardingScreen from '@/app/onboarding';

SplashScreen.preventAutoHideAsync();

function Gate() {
  const { profile, ready } = useProfile();
  if (!ready) return <View style={{ flex: 1, backgroundColor: '#23519D' }} />;
  if (!profile) return <OnboardingScreen />;
  return <AppTabs />;
}

export default function TabLayout() {
  return (
    <ThemeProvider value={DefaultTheme}>
      <LangProvider>
        <ProfileProvider>
          <CartProvider>
            <WishlistProvider>
              {Platform.OS === 'android' && <StatusBar backgroundColor="#23519D" barStyle="light-content" />}
              <AnimatedSplashOverlay />
              <Gate />
            </WishlistProvider>
          </CartProvider>
        </ProfileProvider>
      </LangProvider>
    </ThemeProvider>
  );
}
