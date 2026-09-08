import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { MASTER, TAGLINE } from '@/config/master';
import { useProfile } from '@/store/profile';

export default function OnboardingScreen() {
  const { accept } = useProfile();
  const [mobile, setMobile] = useState('');
  const valid = /^[6-9]\d{9}$/.test(mobile.trim());

  const continuePressed = () => {
    if (valid) void accept(mobile.trim());
  };

  return (
    <View style={styles.blueBg}>
      <SafeAreaView style={styles.safe}>
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={styles.hero}>
            <View style={styles.logoWrap}>
              <ThemedText style={styles.omSymbol}>{'\u0950'}</ThemedText>
            </View>
            <ThemedText style={styles.brand}>{MASTER.displayName.toUpperCase()}</ThemedText>
            <View style={styles.sinceRow}>
              <View style={styles.sinceRule} />
              <ThemedText style={styles.since}>{TAGLINE}</ThemedText>
              <View style={styles.sinceRule} />
            </View>
            <ThemedText style={styles.claim}>Top Jeweller in Palghar District</ThemedText>
          </View>

          <View style={styles.card}>
            <ThemedText style={styles.welcome}>Welcome</ThemedText>
            <ThemedText style={styles.note}>
              This is not a login. No OTP or password is required to browse the app.
            </ThemedText>

            <View style={styles.inputWrap}>
              <View style={styles.prefixWrap}>
                <ThemedText style={styles.flag}>{'\uD83C\uDDEE\uD83C\uDDF3'}</ThemedText>
                <ThemedText style={styles.prefix}>+91</ThemedText>
              </View>
              <View style={styles.inputDivider} />
              <TextInput
                value={mobile}
                onChangeText={(t) => setMobile(t.replace(/\D/g, '').slice(0, 10))}
                placeholder="Enter your mobile number"
                placeholderTextColor="#9CA3AF"
                keyboardType="phone-pad"
                textContentType="telephoneNumber"
                style={styles.input}
                autoFocus
              />
            </View>

            <Pressable
              onPress={continuePressed}
              disabled={!valid}
              style={({ pressed }) => [styles.cta, !valid && styles.ctaDisabled, pressed && { opacity: 0.9 }]}
              accessibilityLabel="Agree and continue">
              <ThemedText style={styles.ctaText}>I Agree &amp; Continue</ThemedText>
            </Pressable>

            <View style={styles.links}>
              <Pressable onPress={() => Linking.openURL('https://aradhana-gold-monitor.onrender.com/')}>
                <ThemedText style={styles.link}>Terms &amp; Conditions</ThemedText>
              </Pressable>
              <ThemedText style={styles.dot}>{'\u00B7'}</ThemedText>
              <Pressable onPress={() => Linking.openURL('https://aradhana-gold-monitor.onrender.com/')}>
                <ThemedText style={styles.link}>Privacy Policy</ThemedText>
              </Pressable>
            </View>

            <ThemedText style={styles.tagline}>{'\u2726'} {TAGLINE} {'\u2726'}</ThemedText>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  blueBg: { flex: 1, backgroundColor: '#23519D' },
  safe: { flex: 1 },
  flex: { flex: 1 },
  hero: { alignItems: 'center', marginTop: 40, marginBottom: 20 },
  logoWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: 'rgba(255,255,255,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(201,168,76,0.4)',
    marginBottom: 14,
  },
  omSymbol: { fontSize: 36, color: '#C9A84C' },
  brand: { color: '#FFFFFF', fontSize: 24, fontWeight: '700', letterSpacing: 3 },
  sinceRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 10 },
  sinceRule: { width: 28, height: 1, backgroundColor: 'rgba(201,168,76,0.5)' },
  since: { color: '#C9A84C', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase' },
  claim: { color: 'rgba(255,255,255,0.65)', fontSize: 11.5, marginTop: 6 },
  card: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    padding: 24,
    paddingTop: 28,
    gap: 14,
  },
  welcome: { fontSize: 24, fontWeight: '700', color: '#1A1A2E' },
  note: { fontSize: 13, color: '#6B7280', marginTop: -4, lineHeight: 18 },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: '#E5E1D8',
    borderRadius: 14,
    paddingHorizontal: 4,
    height: 56,
    backgroundColor: '#FFFBF5',
  },
  prefixWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingLeft: 12,
    paddingRight: 8,
  },
  flag: { fontSize: 18 },
  prefix: { fontSize: 15, fontWeight: '600', color: '#1A1A2E' },
  inputDivider: { width: 1, height: 28, backgroundColor: '#E5E1D8' },
  input: { flex: 1, fontSize: 16, color: '#1A1A2E', paddingVertical: 0, paddingLeft: 10, paddingRight: 14 },
  cta: {
    backgroundColor: '#23519D',
    borderRadius: 14,
    alignItems: 'center',
    paddingVertical: 16,
    marginTop: 4,
  },
  ctaDisabled: { backgroundColor: '#B9C8E0' },
  ctaText: { color: '#FFFFFF', fontSize: 16, fontWeight: '700', letterSpacing: 0.5 },
  links: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, marginTop: 2 },
  link: { color: '#23519D', fontSize: 12.5, textDecorationLine: 'underline' },
  dot: { color: '#9CA3AF', fontSize: 16 },
  tagline: {
    textAlign: 'center',
    color: '#C9A84C',
    fontSize: 10.5,
    letterSpacing: 2,
    textTransform: 'uppercase',
    marginTop: 'auto',
    marginBottom: 4,
  },
});
