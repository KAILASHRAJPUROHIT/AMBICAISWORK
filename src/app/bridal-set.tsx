import { useState, useMemo } from 'react';
import { Image, Linking, Pressable, ScrollView, Share, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius, Shadow } from '@/constants/theme';
import { fetchRateSnapshot, formatInr, type RateSnapshot } from '@/services/rates';
import { products, imageFor, is3DEnabled, type Product } from '@/services/products';
import { estimateMetalValue } from '@/services/pricing';
import { MASTER } from '@/config/master';

type SetSlot = {
  id: string;
  label: string;
  icon: string;
  products: Product[];
  selected: Product | null;
};

const SLOTS: Omit<SetSlot, 'products' | 'selected'>[] = [
  { id: 'necklace', label: 'Necklace', icon: '\uD83D\uDCFF' },
  { id: 'earrings', label: 'Earrings', icon: '\uD83D\uDC8D' },
  { id: 'bangles', label: 'Bangles', icon: '\u2B50' },
  { id: 'ring', label: 'Ring', icon: '\uD83D\uDC8D' },
];

export default function BridalSetBuilder() {
  const router = useRouter();
  const [snap, setSnap] = useState<RateSnapshot | null>(null);
  const [slots, setSlots] = useState<SetSlot[]>(
    SLOTS.map((s) => ({
      ...s,
      products: products.filter((p) => {
        if (s.id === 'necklace') return p.category.includes('necklace') || p.category.includes('neck');
        if (s.id === 'earrings') return p.category.includes('earing') || p.category.includes('jhumka');
        if (s.id === 'bangles') return p.category.includes('bangle');
        if (s.id === 'ring') return p.category.includes('ring');
        return false;
      }).slice(0, 20),
      selected: null,
    }))
  );

  // Fetch rates on mount
  useMemo(() => {
    fetchRateSnapshot().then(setSnap).catch(() => {});
  }, []);

  const totalWeight = slots.reduce((sum, s) => sum + (s.selected?.threeD?.totalWeight ?? s.selected?.weight ?? 0), 0);
  const totalEstimate = snap ? estimateMetalValue(totalWeight, 22, snap) : null;
  const filledSlots = slots.filter((s) => s.selected).length;

  const selectProduct = (slotIdx: number, product: Product) => {
    setSlots((prev) => {
      const next = [...prev];
      next[slotIdx] = { ...next[slotIdx], selected: product };
      return next;
    });
  };

  const removeProduct = (slotIdx: number) => {
    setSlots((prev) => {
      const next = [...prev];
      next[slotIdx] = { ...next[slotIdx], selected: null };
      return next;
    });
  };

  const buildWhatsAppMessage = () => {
    const parts = [
      `Namaste ${MASTER.displayName}`,
      '',
      'I would like to enquire about a Bridal Set:',
      '',
    ];
    slots.forEach((s) => {
      if (s.selected) {
        parts.push(`${s.icon} ${s.label}: ${s.selected.categoryName} (${s.selected.label})`);
        if (s.selected.threeD?.totalWeight) {
          parts.push(`   Weight: ${s.selected.threeD.totalWeight}g`);
        }
      }
    });
    parts.push('');
    parts.push(`Total estimated weight: ${totalWeight.toFixed(2)}g`);
    if (totalEstimate) {
      parts.push(`Estimated metal value: \u20B9${formatInr(totalEstimate.metalValue)} (excl. making/stone/GST)`);
    }
    parts.push('', 'Please share the set details and availability.');
    return parts.join('\n');
  };

  const enquire = () => {
    const text = encodeURIComponent(buildWhatsAppMessage());
    Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
  };

  const share = () => {
    const msg = [
      `Bridal Set from ${MASTER.displayName}`,
      '',
      ...slots.filter(s => s.selected).map(s => `${s.label}: ${s.selected!.label}`),
      '',
      `Total: ${totalWeight.toFixed(2)}g`,
      totalEstimate ? `Est. \u20B9${formatInr(totalEstimate.metalValue)}` : '',
      '',
      'Configure in the Aradhana Jewellers app.',
    ].filter(Boolean).join('\n');
    void Share.share({ message: msg });
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.headerBar}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.headerBtn}>
            <ThemedText style={styles.headerBtnText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.headerTitle}>Build Your Bridal Set</ThemedText>
          <Pressable onPress={share} hitSlop={12} style={styles.headerBtn}>
            <ThemedText style={styles.headerBtnText}>{'\u2197'}</ThemedText>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {/* Progress */}
          <View style={styles.progressCard}>
            <View style={styles.progressHeader}>
              <ThemedText style={styles.progressTitle}>Set Progress</ThemedText>
              <ThemedText style={styles.progressCount}>{filledSlots}/4 items</ThemedText>
            </View>
            <View style={styles.progressBar}>
              {slots.map((s, i) => (
                <View key={s.id} style={[styles.progressDot, s.selected && styles.progressDotActive]} />
              ))}
            </View>
            <ThemedText style={styles.progressHint}>
              {filledSlots === 0
                ? 'Select one item from each category to build your set'
                : filledSlots < 4
                ? `${4 - filledSlots} more ${filledSlots === 3 ? 'item' : 'items'} needed`
                : 'Set complete! Enquire for the full bridal look.'}
            </ThemedText>
          </View>

          {/* Slot Sections */}
          {slots.map((slot, slotIdx) => (
            <View key={slot.id} style={styles.slotSection}>
              <View style={styles.slotHeader}>
                <ThemedText style={styles.slotIcon}>{slot.icon}</ThemedText>
                <View style={{ flex: 1 }}>
                  <ThemedText style={styles.slotLabel}>{slot.label}</ThemedText>
                  <ThemedText style={styles.slotCount}>{slot.products.length} designs available</ThemedText>
                </View>
                {slot.selected && (
                  <Pressable onPress={() => removeProduct(slotIdx)} style={styles.removeBtn}>
                    <ThemedText style={styles.removeBtnText}>Change</ThemedText>
                  </Pressable>
                )}
              </View>

              {slot.selected ? (
                <View style={[styles.selectedCard, Shadow.sm]}>
                  <View style={styles.selectedImgWrap}>
                    {imageFor(slot.selected) ? (
                      <Image source={imageFor(slot.selected)} style={styles.selectedImg} resizeMode="contain" />
                    ) : (
                      <View style={[styles.selectedImg, { backgroundColor: '#F8F6F3' }]} />
                    )}
                  </View>
                  <View style={styles.selectedInfo}>
                    <ThemedText style={styles.selectedName}>{slot.selected.categoryName}</ThemedText>
                    <ThemedText style={styles.selectedLabel}>{slot.selected.label}</ThemedText>
                    <View style={styles.selectedMeta}>
                      {slot.selected.karat && <ThemedText style={styles.selectedMetaText}>{slot.selected.karat}K</ThemedText>}
                      {(slot.selected.threeD?.totalWeight ?? slot.selected.weight) && (
                        <ThemedText style={styles.selectedMetaText}>{(slot.selected.threeD?.totalWeight ?? slot.selected.weight)?.toFixed(2)}g</ThemedText>
                      )}
                      {is3DEnabled(slot.selected) && (
                        <View style={styles.badge3D}><ThemedText style={styles.badge3DText}>3D</ThemedText></View>
                      )}
                    </View>
                  </View>
                  <Pressable onPress={() => router.push(`/product/${slot.selected!.id}`)} style={styles.viewBtn}>
                    <ThemedText style={styles.viewBtnText}>{'\u203A'}</ThemedText>
                  </Pressable>
                </View>
              ) : (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.productRow}>
                  {slot.products.slice(0, 10).map((p) => (
                    <Pressable
                      key={p.id}
                      onPress={() => selectProduct(slotIdx, p)}
                      style={[styles.productCard, Shadow.sm]}
                      accessibilityLabel={`Select ${p.categoryName} ${p.label}`}>
                      <View style={styles.productImgWrap}>
                        {imageFor(p) ? (
                          <Image source={imageFor(p)} style={styles.productImg} resizeMode="contain" />
                        ) : (
                          <View style={[styles.productImg, { backgroundColor: '#F8F6F3' }]} />
                        )}
                        {is3DEnabled(p) && <View style={styles.cardBadge3D}><ThemedText style={styles.cardBadge3DText}>3D</ThemedText></View>}
                      </View>
                      <View style={styles.productInfo}>
                        <ThemedText style={styles.productMeta} numberOfLines={1}>{p.label}</ThemedText>
                        <ThemedText style={styles.productWeight} numberOfLines={1}>
                          {[p.karat ? `${p.karat}K` : null, (p.threeD?.totalWeight ?? p.weight) ? `${(p.threeD?.totalWeight ?? p.weight)?.toFixed(1)}g` : null].filter(Boolean).join(' \u00B7 ')}
                        </ThemedText>
                      </View>
                    </Pressable>
                  ))}
                </ScrollView>
              )}
            </View>
          ))}

          {/* Combined Estimate */}
          {filledSlots > 0 && (
            <View style={[styles.estimateCard, Shadow.sm]}>
              <View style={styles.estimateHeader}>
                <ThemedText style={styles.estimateLabel}>Combined Estimate</ThemedText>
                {snap && (
                  <View style={styles.liveTag}>
                    <View style={styles.liveDot} />
                    <ThemedText style={styles.liveText}>LIVE</ThemedText>
                  </View>
                )}
              </View>
              <View style={styles.estimateRow}>
                <View style={styles.estimateCell}>
                  <ThemedText style={styles.estimateValue}>{totalWeight.toFixed(1)}g</ThemedText>
                  <ThemedText style={styles.estimateCellLabel}>Total Weight</ThemedText>
                </View>
                <View style={styles.estimateDivider} />
                <View style={styles.estimateCell}>
                  <ThemedText style={styles.estimateValue}>
                    {totalEstimate ? `\u20B9${formatInr(totalEstimate.metalValue)}` : '--'}
                  </ThemedText>
                  <ThemedText style={styles.estimateCellLabel}>Metal Value</ThemedText>
                </View>
              </View>
              <ThemedText style={styles.estimateDisclaimer}>
                Estimated metal value only. Excludes making charges, stones, GST, and final counter weight.
              </ThemedText>
            </View>
          )}

          {/* Actions */}
          <View style={styles.actions}>
            <Pressable onPress={enquire} style={[styles.enquireBtn, Shadow.sm]} accessibilityLabel="Enquire about set">
              <ThemedText style={styles.enquireBtnText}>
                {'\uD83D\uDCAC'} Enquire on WhatsApp
              </ThemedText>
            </Pressable>
          </View>

          <View style={{ height: 20 }} />
        </ScrollView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  headerBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#F0ECE4' },
  headerBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#F8F6F3', alignItems: 'center', justifyContent: 'center' },
  headerBtnText: { fontSize: 18, color: '#1A1A2E' },
  headerTitle: { flex: 1, fontSize: 16, fontWeight: '600', color: '#1A1A2E', textAlign: 'center', marginHorizontal: 8 },
  content: { gap: 16, paddingBottom: Spacing.six, paddingTop: 14 },

  /* Progress */
  progressCard: { marginHorizontal: 16, backgroundColor: '#23519D', borderRadius: BorderRadius.xl, padding: 16, gap: 8 },
  progressHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  progressTitle: { color: '#C9A84C', fontSize: 11, fontWeight: '700', letterSpacing: 1.5, textTransform: 'uppercase' },
  progressCount: { color: '#FFFFFF', fontSize: 12, fontWeight: '600' },
  progressBar: { flexDirection: 'row', gap: 8 },
  progressDot: { flex: 1, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.2)' },
  progressDotActive: { backgroundColor: '#C9A84C' },
  progressHint: { color: 'rgba(255,255,255,0.6)', fontSize: 12 },

  /* Slots */
  slotSection: { gap: 10 },
  slotHeader: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, gap: 10 },
  slotIcon: { fontSize: 20 },
  slotLabel: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  slotCount: { fontSize: 11, color: '#9CA3AF' },
  removeBtn: { backgroundColor: '#F8F6F3', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: '#E5E1D8' },
  removeBtnText: { fontSize: 11, fontWeight: '600', color: '#6B7280' },

  /* Selected card */
  selectedCard: { marginHorizontal: 16, flexDirection: 'row', backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden' },
  selectedImgWrap: { width: 100, height: 100, backgroundColor: '#FFFBF5' },
  selectedImg: { width: '100%', height: '100%' },
  selectedInfo: { flex: 1, padding: 12, gap: 2, justifyContent: 'center' },
  selectedName: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  selectedLabel: { fontSize: 12, color: '#6B7280' },
  selectedMeta: { flexDirection: 'row', gap: 6, marginTop: 4 },
  selectedMetaText: { fontSize: 11, fontWeight: '600', color: '#23519D', backgroundColor: '#EEF2FF', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  badge3D: { backgroundColor: '#4338CA', borderRadius: 4, paddingHorizontal: 4, paddingVertical: 1 },
  badge3DText: { fontSize: 8, fontWeight: '700', color: '#FFFFFF' },
  viewBtn: { width: 36, alignItems: 'center', justifyContent: 'center' },
  viewBtnText: { fontSize: 20, color: '#C9A84C' },

  /* Product row */
  productRow: { paddingHorizontal: 16, gap: 10 },
  productCard: { width: 120, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden' },
  productImgWrap: { width: '100%', aspectRatio: 1, backgroundColor: '#FFFBF5', position: 'relative' },
  productImg: { width: '100%', height: '100%' },
  cardBadge3D: { position: 'absolute', top: 6, right: 6, backgroundColor: '#4338CA', borderRadius: 4, paddingHorizontal: 4, paddingVertical: 2 },
  cardBadge3DText: { fontSize: 8, fontWeight: '700', color: '#FFFFFF' },
  productInfo: { padding: 8, gap: 2 },
  productMeta: { fontSize: 11, fontWeight: '600', color: '#1A1A2E' },
  productWeight: { fontSize: 10, color: '#9CA3AF' },

  /* Estimate */
  estimateCard: { marginHorizontal: 16, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.xl, padding: 16, borderWidth: 1, borderColor: '#E5E1D8' },
  estimateHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  estimateLabel: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  liveTag: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(22,163,74,0.1)', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  liveDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: '#16A34A' },
  liveText: { fontSize: 9, fontWeight: '700', color: '#16A34A', letterSpacing: 1 },
  estimateRow: { flexDirection: 'row', gap: 12 },
  estimateCell: { flex: 1, alignItems: 'center', gap: 4 },
  estimateValue: { fontSize: 20, fontWeight: '700', color: '#23519D' },
  estimateCellLabel: { fontSize: 11, color: '#6B7280' },
  estimateDivider: { width: 1, backgroundColor: '#F0ECE4' },
  estimateDisclaimer: { fontSize: 11, color: '#9CA3AF', lineHeight: 16, marginTop: 12 },

  /* Actions */
  actions: { marginHorizontal: 16 },
  enquireBtn: { alignItems: 'center', backgroundColor: '#16A34A', borderRadius: BorderRadius.md, paddingVertical: 14 },
  enquireBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
});
