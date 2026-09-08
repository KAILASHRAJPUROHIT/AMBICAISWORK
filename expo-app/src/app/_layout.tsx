import { DefaultTheme, ThemeProvider } from 'expo-router';
import { Animated, Platform, StatusBar, View } from 'react-native';
import { useEffect, useState } from 'react';
import * as SplashScreen from 'expo-splash-screen';

import AppTabs from '@/components/app-tabs';
import { WishlistProvider } from '@/store/wishlist';
import { ProfileProvider, useProfile } from '@/store/profile';
import { CartProvider } from '@/store/cart';
import { EnquiryProvider } from '@/store/enquiries';
import { LangProvider } from '@/store/lang';
import OnboardingScreen from '@/app/onboarding';

// Keep expo splash visible until we're ready to reveal content
SplashScreen.preventAutoHideAsync();

function Gate() {
  const { profile, ready } = useProfile();
  const [fadeAnim] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (ready) {
      // Hide expo splash, then fade in the content
      SplashScreen.hideAsync().then(() => {
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 400,
          useNativeDriver: true,
        }).start();
      });
    }
  }, [ready, fadeAnim]);

  if (!ready) return <View style={{ flex: 1, backgroundColor: '#23519D' }} />;

  return (
    <Animated.View style={{ flex: 1, opacity: fadeAnim }}>
      {!profile ? <OnboardingScreen /> : <AppTabs />}
    </Animated.View>
  );
}

export default function TabLayout() {
  return (
    <ThemeProvider value={DefaultTheme}>
      <LangProvider>
        <ProfileProvider>
          <CartProvider>
            <EnquiryProvider>
              <WishlistProvider>
                {Platform.OS === 'android' && <StatusBar backgroundColor="#23519D" barStyle="light-content" />}
                <Gate />
              </WishlistProvider>
            </EnquiryProvider>
          </CartProvider>
        </ProfileProvider>
      </LangProvider>
    </ThemeProvider>
  );
}
