import { Image, Linking, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BorderRadius, Shadow } from '@/constants/theme';
import { MASTER } from '@/config/master';

export default function SipScreen() {
  const router = useRouter();

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.title}>Gold Savings Plan</ThemedText>
          <View style={{ width: 36 }} />
        </View>

        {/* Hero Image */}
        <View style={[styles.heroWrap, Shadow.md]}>
          <Image source={require('@/assets/aradhana/sip_main.jpg')} style={styles.heroImg} />
        </View>

        {/* Plan Info */}
        <View style={[styles.infoCard, Shadow.sm]}>
          <ThemedText style={styles.infoTitle}>How It Works</ThemedText>
          <View style={styles.stepRow}>
            <View style={styles.stepBadge}><ThemedText style={styles.stepBadgeText}>1</ThemedText></View>
            <View style={{ flex: 1 }}>
              <ThemedText style={styles.stepTitle}>Start Your Plan</ThemedText>
              <ThemedText style={styles.stepDesc}>Choose your monthly instalment amount and duration.</ThemedText>
            </View>
          </View>
          <View style={styles.stepRow}>
            <View style={styles.stepBadge}><ThemedText style={styles.stepBadgeText}>2</ThemedText></View>
            <View style={{ flex: 1 }}>
              <ThemedText style={styles.stepTitle}>Monthly Payments</ThemedText>
              <ThemedText style={styles.stepDesc}>Pay monthly and accumulate gold at the current rate.</ThemedText>
            </View>
          </View>
          <View style={styles.stepRow}>
            <View style={styles.stepBadge}><ThemedText style={styles.stepBadgeText}>3</ThemedText></View>
            <View style={{ flex: 1 }}>
              <ThemedText style={styles.stepTitle}>Redeem Jewellery</ThemedText>
              <ThemedText style={styles.stepDesc}>Use your accumulated gold value to purchase jewellery.</ThemedText>
            </View>
          </View>
        </View>

        {/* Calculator */}
        <View style={[styles.calcCard, Shadow.sm]}>
          <ThemedText style={styles.calcTitle}>Estimate Your Plan</ThemedText>
          <View style={styles.calcRow}>
            <View style={styles.calcItem}>
              <ThemedText style={styles.calcLabel}>Monthly Amount</ThemedText>
              <ThemedText style={styles.calcValue}>Customizable</ThemedText>
            </View>
            <View style={styles.calcDivider} />
            <View style={styles.calcItem}>
              <ThemedText style={styles.calcLabel}>Duration</ThemedText>
              <ThemedText style={styles.calcValue}>Flexible</ThemedText>
            </View>
          </View>
          <ThemedText style={styles.calcNote}>
            Contact the showroom for exact terms, instalment amounts and benefits.
          </ThemedText>
        </View>

        {/* Details Image */}
        <View style={[styles.detailsWrap, Shadow.sm]}>
          <Image source={require('@/assets/aradhana/sip_details.jpg')} style={styles.detailsImg} />
        </View>

        {/* CTA */}
        <Pressable
          onPress={() => {
            const text = encodeURIComponent(`Namaste ${MASTER.displayName}, I am interested in the Gold Savings Plan. Please share details.`);
            Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
          }}
          style={styles.cta}>
          <ThemedText style={styles.ctaText}>{'\uD83D\uDCAC'} Enquire on WhatsApp</ThemedText>
        </Pressable>

        <View style={styles.disclaimer}>
          <ThemedText style={styles.disclaimerText}>
            Plan duration, instalment amount and benefits will be updated once the final approved
            scheme terms are available from {MASTER.displayName}.
          </ThemedText>
        </View>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F8F6F3',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  backText: { fontSize: 18, color: '#1A1A2E' },
  title: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },

  heroWrap: {
    marginHorizontal: 16,
    borderRadius: BorderRadius.xl,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  heroImg: { width: '100%', aspectRatio: 800 / 650 },

  infoCard: {
    marginHorizontal: 16,
    marginTop: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    padding: 16,
    gap: 14,
  },
  infoTitle: { fontSize: 17, fontWeight: '700', color: '#1A1A2E' },
  stepRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  stepBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#23519D',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepBadgeText: { fontSize: 13, fontWeight: '700', color: '#FFFFFF' },
  stepTitle: { fontSize: 14, fontWeight: '600', color: '#1A1A2E', marginBottom: 2 },
  stepDesc: { fontSize: 12, color: '#6B7280', lineHeight: 16 },

  calcCard: {
    marginHorizontal: 16,
    marginTop: 12,
    backgroundColor: '#FDF8ED',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E8D9A8',
    padding: 16,
    gap: 10,
  },
  calcTitle: { fontSize: 15, fontWeight: '700', color: '#1A1A2E' },
  calcRow: { flexDirection: 'row', gap: 12 },
  calcItem: { flex: 1, gap: 4 },
  calcLabel: { fontSize: 11, color: '#6B7280' },
  calcValue: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  calcDivider: { width: 1, backgroundColor: '#E8D9A8' },
  calcNote: { fontSize: 12, color: '#6B7280', fontStyle: 'italic' },

  detailsWrap: {
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  detailsImg: { width: '100%', aspectRatio: 800 / 340 },

  cta: {
    marginHorizontal: 16,
    marginTop: 16,
    backgroundColor: '#16A34A',
    borderRadius: BorderRadius.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  ctaText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },

  disclaimer: {
    marginHorizontal: 16,
    marginTop: 12,
    backgroundColor: '#F8F6F3',
    borderRadius: BorderRadius.md,
    padding: 12,
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  disclaimerText: { fontSize: 11, color: '#6B7280', lineHeight: 16 },
});
