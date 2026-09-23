import { Image, Linking, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MASTER } from '@/config/master';
import { BorderRadius, Shadow } from '@/constants/theme';

export default function GiftVoucherScreen() {
  const router = useRouter();

  const enquire = () => {
    const text = encodeURIComponent(
      `Namaste ${MASTER.displayName}, I would like to know more about E-Gift Vouchers.`,
    );
    Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <ThemedText style={styles.backText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.title}>E-Gift Voucher</ThemedText>
          <View style={{ width: 36 }} />
        </View>

        <View style={[styles.heroCard, Shadow.md]}>
          <Image
            source={require('@/assets/aradhana/e_gift_voucher.jpg')}
            style={styles.voucher}
          />
        </View>

        <View style={[styles.infoCard, Shadow.sm]}>
          <ThemedText style={styles.infoTitle}>Give the Gift of Choice</ThemedText>
          <ThemedText style={styles.infoDesc}>
            E-Gift vouchers from {MASTER.displayName} can be used against gold and silver jewellery
            across all collections. Perfect for weddings, festivals, and special occasions.
          </ThemedText>
          <View style={styles.infoDivider} />
          <View style={styles.featureRow}>
            <ThemedText style={styles.featureIcon}>{'\u2713'}</ThemedText>
            <ThemedText style={styles.featureText}>Redeemable across all collections</ThemedText>
          </View>
          <View style={styles.featureRow}>
            <ThemedText style={styles.featureIcon}>{'\u2713'}</ThemedText>
            <ThemedText style={styles.featureText}>Available in multiple denominations</ThemedText>
          </View>
          <View style={styles.featureRow}>
            <ThemedText style={styles.featureIcon}>{'\u2713'}</ThemedText>
            <ThemedText style={styles.featureText}>Terms and validity confirmed at issuance</ThemedText>
          </View>
        </View>

        <Pressable onPress={enquire} style={styles.cta} accessibilityLabel="Enquire about vouchers">
          <ThemedText style={styles.ctaText}>{'\uD83D\uDCAC'} Enquire on WhatsApp</ThemedText>
        </Pressable>

        <View style={styles.disclaimer}>
          <ThemedText style={styles.disclaimerText}>
            Terms, validity and denominations are confirmed by the showroom at issuance.
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

  heroCard: {
    marginHorizontal: 16,
    borderRadius: BorderRadius.xl,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  voucher: { width: '100%', aspectRatio: 600 / 350 },

  infoCard: {
    marginHorizontal: 16,
    marginTop: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    padding: 16,
    gap: 10,
  },
  infoTitle: { fontSize: 17, fontWeight: '700', color: '#1A1A2E' },
  infoDesc: { fontSize: 13, color: '#6B7280', lineHeight: 19 },
  infoDivider: { height: 1, backgroundColor: '#F0ECE4' },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  featureIcon: { fontSize: 14, color: '#16A34A', fontWeight: '700' },
  featureText: { fontSize: 13, color: '#1A1A2E', flex: 1 },

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
