import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, type Href } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Brand, Spacing, BorderRadius } from '@/constants/theme';
import { MASTER } from '@/config/master';
import { useCart } from '@/store/cart';

const sections = [
  {
    title: 'Shop',
    items: [
      { label: 'Collections', route: '/collections', icon: '\uD83D\uDDBC\uFE0F' },
      { label: 'Today\u2019s Gold Rate', route: '/gold-rate', icon: '\uD83D\uDCB0' },
      { label: 'Gold Savings Plan', route: '/sip', icon: '\uD83D\uDCC8' },
      { label: 'E-Gift Vouchers', route: '/gift-voucher', icon: '\uD83C\uDF81' },
    ],
  },
  {
    title: 'Account',
    items: [
      { label: 'My Wishlist', route: '/wishlist', icon: '\u2661' },
      { label: 'My Cart', route: '/cart', icon: '\uD83D\uDED2' },
    ],
  },
  {
    title: 'Store',
    items: [
      { label: 'Showroom & Directions', route: '/store', icon: '\uD83D\uDCCD' },
      { label: 'Bank Details & Payments', route: '/bank-details', icon: '\uD83C\uDFE6' },
    ],
  },
  {
    title: 'Connect',
    items: [
      { label: `WhatsApp Us`, href: Brand.whatsapp, icon: '\uD83D\uDCAC' },
      { label: 'Instagram', href: Brand.instagram, icon: '\uD83D\uDCF4' },
    ],
  },
];

export default function MoreScreen() {
  const router = useRouter();
  const { count } = useCart();

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <ScrollViewWrapper>
          {/* Brand Header */}
          <View style={styles.brandHeader}>
            <View style={styles.brandLogo}>
              <ThemedText style={styles.omSymbol}>{'\u0950'}</ThemedText>
            </View>
            <ThemedText style={styles.brandName}>{MASTER.displayName}</ThemedText>
            <ThemedText style={styles.brandTag}>{Brand.tagline}</ThemedText>
            <View style={styles.brandDivider} />
            <ThemedText style={styles.brandAddress}>{MASTER.shortAddress}</ThemedText>
          </View>

          {/* Sections */}
          {sections.map((section) => (
            <View key={section.title} style={styles.section}>
              <ThemedText style={styles.sectionTitle}>{section.title.toUpperCase()}</ThemedText>
              <View style={styles.sectionCard}>
                {section.items.map((item, idx) => (
                  <Pressable
                    key={item.label}
                    onPress={() => {
                      if ('route' in item && item.route) router.push(item.route as Href);
                      else if ('href' in item && item.href) Linking.openURL(item.href);
                    }}
                    accessibilityLabel={item.label}
                    style={({ pressed }) => [styles.row, pressed && { backgroundColor: '#F8F6F3' }]}>
                    <View style={styles.rowLeft}>
                      <ThemedText style={styles.rowIcon}>{item.icon}</ThemedText>
                      <ThemedText style={styles.rowLabel}>{item.label}</ThemedText>
                      {'route' in item && item.route === '/cart' && count > 0 && (
                        <View style={styles.badge}>
                          <ThemedText style={styles.badgeText}>{count}</ThemedText>
                        </View>
                      )}
                    </View>
                    <ThemedText style={styles.rowArrow}>{'\u203A'}</ThemedText>
                    {idx < section.items.length - 1 && <View style={styles.rowDivider} />}
                  </Pressable>
                ))}
              </View>
            </View>
          ))}

          {/* Footer */}
          <View style={styles.footer}>
            <ThemedText style={styles.footerText}>{MASTER.legalName}</ThemedText>
            <ThemedText style={styles.footerSub}>Proprietorship \u00B7 GSTIN: {MASTER.gstin}</ThemedText>
            <ThemedText style={styles.footerSub}>{MASTER.email}</ThemedText>
            <ThemedText style={styles.footerTagline}>
              Gold &amp; Silver Jewellery \u00B7 Hallmarked 916 \u00B7 Boisar, Palghar
            </ThemedText>
          </View>
        </ScrollViewWrapper>
      </SafeAreaView>
    </ThemedView>
  );
}

function ScrollViewWrapper({ children }: { children: React.ReactNode }) {
  return <ScrollView contentContainerStyle={{ paddingBottom: Spacing.six }}>{children}</ScrollView>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },

  /* Brand Header */
  brandHeader: {
    alignItems: 'center',
    paddingVertical: 24,
    paddingHorizontal: 20,
    gap: 6,
  },
  brandLogo: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#23519D',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  omSymbol: { fontSize: 30, color: '#C9A84C' },
  brandName: { fontSize: 20, fontWeight: '700', color: '#1A1A2E', letterSpacing: 0.5 },
  brandTag: { fontSize: 12, color: '#C9A84C', letterSpacing: 1.5, textTransform: 'uppercase' },
  brandDivider: { width: 40, height: 2, backgroundColor: '#C9A84C', borderRadius: 1, marginVertical: 4 },
  brandAddress: { fontSize: 11, color: '#6B7280' },

  /* Sections */
  section: { paddingHorizontal: 16, marginBottom: 8 },
  sectionTitle: { fontSize: 11, fontWeight: '700', color: '#9CA3AF', letterSpacing: 1.5, marginBottom: 8, marginLeft: 4 },
  sectionCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: '#E5E1D8',
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  rowLeft: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowIcon: { fontSize: 18, width: 24, textAlign: 'center' },
  rowLabel: { fontSize: 14, fontWeight: '500', color: '#1A1A2E' },
  rowArrow: { fontSize: 20, color: '#C9A84C', fontWeight: '600' },
  rowDivider: { position: 'absolute', bottom: 0, left: 52, right: 0, height: 1, backgroundColor: '#F0ECE4' },
  badge: {
    backgroundColor: '#23519D',
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { color: '#FFFFFF', fontSize: 10, fontWeight: '700' },

  /* Footer */
  footer: { alignItems: 'center', paddingVertical: 24, gap: 4 },
  footerText: { fontSize: 13, fontWeight: '600', color: '#1A1A2E' },
  footerSub: { fontSize: 11, color: '#9CA3AF' },
  footerTagline: { fontSize: 11, color: '#C9A84C', letterSpacing: 0.5, marginTop: 4 },
});
