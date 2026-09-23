import { useEffect, useState, useMemo } from 'react';
import { Image, Linking, Pressable, ScrollView, Share, StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius, Shadow } from '@/constants/theme';
import { fetchRateSnapshot, formatInr, type RateSnapshot } from '@/services/rates';
import { byCategory, getById, imageFor, is3DEnabled, type MaterialVariant } from '@/services/products';
import { estimate3DProduct } from '@/services/pricing';
import { MASTER } from '@/config/master';
import { useWishlist } from '@/store/wishlist';

// Lazy-load 3D viewer to avoid bundling Three.js on 2D-only screens
const ViewerComponent: React.ComponentType<any> | null = (() => {
  try {
    return require('@/components/three/JewelleryViewer').default;
  } catch {
    return null;
  }
})();

const HOTSPOTS = [
  { id: 'hallmark', label: 'Hallmark', icon: '\u2713' },
  { id: 'stone', label: 'Stone Setting', icon: '\u2666' },
  { id: 'clasp', label: 'Clasp', icon: '\u2630' },
  { id: 'side', label: 'Side Profile', icon: '\u2194' },
] as const;

type HotspotId = typeof HOTSPOTS[number]['id'];

export default function ProductScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { toggle, has } = useWishlist();
  const [snap, setSnap] = useState<RateSnapshot | null>(null);
  const [imgError, setImgError] = useState(false);
  const [selectedVariant, setSelectedVariant] = useState<MaterialVariant | null>(null);
  const [selectedKarat, setSelectedKarat] = useState<18 | 22>(22);
  const [activeHotspot, setActiveHotspot] = useState<HotspotId | null>(null);
  const [viewerLoaded, setViewerLoaded] = useState(false);
  const [viewerError, setViewerError] = useState(false);

  const product = id ? getById(id) : undefined;
  const has3D = product ? is3DEnabled(product) : false;
  const show3D = has3D && ViewerComponent && !viewerError;

  // Derive selected variant/purity from product (no setState in effect needed)
  const effectiveVariant = selectedVariant ?? product?.threeD?.materialVariants?.[0] ?? null;
  const effectiveKarat = selectedKarat;

  useEffect(() => {
    let cancelled = false;
    fetchRateSnapshot()
      .then((s) => { if (!cancelled) setSnap(s); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Initialize variant selection from product defaults

  // Compute price using shared service
  const priceBreakdown = useMemo(() => {
    if (!product) return null;
    return estimate3DProduct(product, effectiveKarat, snap);
  }, [product, effectiveKarat, snap]);

  // Legacy estimate for 2D products
  const legacyEstimate =
    product?.weight && snap
      ? Math.round((product.weight * snap.published.rate22kt) / 10)
      : null;

  if (!product) {
    return (
      <ThemedView style={styles.center}>
        <SafeAreaView style={styles.center}>
          <ThemedText style={styles.notFoundTitle}>Product Not Found</ThemedText>
          <ThemedText style={styles.notFoundSub}>This item may no longer be available.</ThemedText>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <ThemedText style={styles.backBtnText}>Go Back</ThemedText>
          </Pressable>
        </SafeAreaView>
      </ThemedView>
    );
  }

  const img = imageFor(product);
  const similar = byCategory(product.category)
    .filter((p) => p.id !== product.id)
    .slice(0, 8);
  const wish = has(product.id);

  const buildWhatsAppMessage = () => {
    const parts = [
      `Namaste ${MASTER.displayName}`,
      '',
      `I am interested in:`,
      `\u2022 Product: ${product.categoryName} (${product.label})`,
      `\u2022 Product ID: ${product.id}`,
    ];

    if (effectiveVariant) {
      parts.push(`\u2022 Metal: ${effectiveVariant.label}`);
    }
    if (effectiveKarat) {
      parts.push(`\u2022 Purity: ${effectiveKarat}K`);
    }
    if (product.threeD?.totalWeight) {
      parts.push(`\u2022 Weight: ${product.threeD.totalWeight}g`);
    }
    if (priceBreakdown) {
      parts.push(`\u2022 Estimated metal value: \u20B9${formatInr(priceBreakdown.metalValue)} (excl. making/stone/GST)`);
    }

    parts.push('', 'Please share details and availability.');

    return parts.join('\n');
  };

  const enquire = () => {
    const text = encodeURIComponent(buildWhatsAppMessage());
    Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
  };

  const share = () => {
    const msg = [
      `${product.categoryName} \u2014 ${product.label}`,
      `From ${MASTER.displayName}, Boisar`,
      selectedVariant ? `Metal: ${selectedVariant.label}` : '',
      product.threeD?.totalWeight ? `Weight: ${product.threeD.totalWeight}g` : '',
      '',
      'View in the Aradhana Jewellers app.',
    ].filter(Boolean).join('\n');
    void Share.share({ message: msg });
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        {/* Header Bar */}
        <View style={styles.headerBar}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.headerBtn} accessibilityLabel="Back">
            <ThemedText style={styles.headerBtnText}>{'\u2190'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.headerTitle} numberOfLines={1}>{product.categoryName}</ThemedText>
          <Pressable onPress={share} hitSlop={12} style={styles.headerBtn} accessibilityLabel="Share">
            <ThemedText style={styles.headerBtnText}>{'\u2197'}</ThemedText>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {/* ── 3D Viewer or 2D Image ── */}
          {show3D && ViewerComponent ? (
            <View style={[styles.viewerCard, Shadow.md]}>
              <ViewerComponent
                product={product}
                activeVariant={effectiveVariant}
                onLoaded={() => setViewerLoaded(true)}
                onError={() => setViewerError(true)}
              />
              {/* Inspect Mode Bar */}
              <View style={styles.inspectBar}>
                <ThemedText style={styles.inspectLabel}>Inspect Craftsmanship</ThemedText>
                <View style={styles.hotspotRow}>
                  {HOTSPOTS.map((h) => (
                    <Pressable
                      key={h.id}
                      onPress={() => setActiveHotspot(activeHotspot === h.id ? null : h.id)}
                      style={[
                        styles.hotspotBtn,
                        activeHotspot === h.id && styles.hotspotBtnActive,
                      ]}
                      accessibilityLabel={h.label}>
                      <ThemedText style={styles.hotspotIcon}>{h.icon}</ThemedText>
                      <ThemedText style={[
                        styles.hotspotLabel,
                        activeHotspot === h.id && styles.hotspotLabelActive,
                      ]}>{h.label}</ThemedText>
                    </Pressable>
                  ))}
                </View>
              </View>
            </View>
          ) : (
            <View style={[styles.imageCard, Shadow.md]}>
              {img && !imgError ? (
                <Image source={img} style={styles.image} resizeMode="contain" onError={() => setImgError(true)} />
              ) : (
                <View style={styles.imagePlaceholder}>
                  <ThemedText style={styles.imagePlaceholderText}>Photo coming soon</ThemedText>
                </View>
              )}
            </View>
          )}

          {/* ── Product Info ── */}
          <View style={styles.infoSection}>
            <View style={styles.infoTop}>
              <View style={{ flex: 1 }}>
                <ThemedText style={styles.productCategory}>{product.categoryName}</ThemedText>
                <ThemedText style={styles.productLabel}>Item {product.label}</ThemedText>
              </View>
              <Pressable onPress={() => toggle(product.id)} style={[styles.heartBtn, wish && styles.heartBtnActive]} accessibilityLabel="Save">
                <ThemedText style={[styles.heartIcon, wish && styles.heartIconActive]}>{wish ? '\u2665' : '\u2661'}</ThemedText>
              </Pressable>
            </View>

            {/* Tags */}
            <View style={styles.tagRow}>
              {(effectiveKarat || product.karat) && (
                <View style={styles.tag}>
                  <ThemedText style={styles.tagText}>{effectiveKarat || product.karat}K Gold</ThemedText>
                </View>
              )}
              {(product.threeD?.totalWeight || product.weight) && (
                <View style={styles.tag}>
                  <ThemedText style={styles.tagText}>{(product.threeD?.totalWeight ?? product.weight)?.toFixed(2)}g</ThemedText>
                </View>
              )}
              <View style={[styles.tag, styles.tagHallmark]}>
                <ThemedText style={[styles.tagText, styles.tagHallmarkText]}>
                  {effectiveKarat === 18 ? '750' : '916'} Hallmarked
                </ThemedText>
              </View>
              {has3D && (
                <View style={[styles.tag, styles.tag3D]}>
                  <ThemedText style={[styles.tagText, styles.tag3DText]}>3D Interactive</ThemedText>
                </View>
              )}
            </View>
          </View>

          {/* ── Material/Purity Switcher (3D products only) ── */}
          {has3D && product.threeD && (
            <View style={styles.switcherSection}>
              {/* Material Variants */}
              {product.threeD.materialVariants.length > 1 && (
                <View style={styles.switcherGroup}>
                  <ThemedText style={styles.switcherLabel}>Metal Colour</ThemedText>
                  <View style={styles.switcherRow}>
                    {product.threeD.materialVariants.map((v) => (
                      <Pressable
                        key={v.id}
                        onPress={() => setSelectedVariant(v)}
                        style={[
                          styles.switcherChip,
                          effectiveVariant?.id === v.id && styles.switcherChipActive,
                        ]}
                        accessibilityLabel={v.label}>
                        <View style={[styles.colorDot, { backgroundColor: v.hexAccent || '#D4A843' }]} />
                        <ThemedText style={[
                          styles.switcherChipText,
                          effectiveVariant?.id === v.id && styles.switcherChipTextActive,
                        ]}>{v.label}</ThemedText>
                      </Pressable>
                    ))}
                  </View>
                </View>
              )}

              {/* Purity Options */}
              {product.threeD.purityOptions.length > 1 && (
                <View style={styles.switcherGroup}>
                  <ThemedText style={styles.switcherLabel}>Gold Purity</ThemedText>
                  <View style={styles.switcherRow}>
                    {product.threeD.purityOptions.map((p) => (
                      <Pressable
                        key={p.karat}
                        onPress={() => setSelectedKarat(p.karat as 18 | 22)}
                        style={[
                          styles.switcherChip,
                          effectiveKarat === p.karat && styles.switcherChipActive,
                        ]}
                        accessibilityLabel={p.label}>
                        <ThemedText style={[
                          styles.switcherChipText,
                          effectiveKarat === p.karat && styles.switcherChipTextActive,
                        ]}>{p.label}</ThemedText>
                      </Pressable>
                    ))}
                  </View>
                </View>
              )}
            </View>
          )}

          {/* ── Price Card ── */}
          <View style={[styles.priceCard, Shadow.sm]}>
            {has3D && priceBreakdown ? (
              <>
                <View style={styles.priceHeader}>
                  <ThemedText style={styles.priceLabel}>Estimated Metal Value</ThemedText>
                  <View style={styles.priceLiveTag}>
                    <View style={styles.priceLiveDot} />
                    <ThemedText style={styles.priceLiveText}>LIVE RATE</ThemedText>
                  </View>
                </View>
                <ThemedText style={styles.priceValue}>{'\u20B9'} {formatInr(priceBreakdown.metalValue)}</ThemedText>
                <ThemedText style={styles.priceCalc}>
                  {priceBreakdown.weight}g \u00D7 {'\u20B9'}{formatInr(priceBreakdown.ratePer10g)}/10g ({priceBreakdown.karatLabel})
                </ThemedText>
                {snap && (
                  <ThemedText style={styles.priceMeta}>
                    Based on today{'\u2019'}s rate \u00B7 Updated {snap.published.atIst} IST
                  </ThemedText>
                )}
                <View style={styles.priceDivider} />
                <ThemedText style={styles.priceDisclaimer}>{priceBreakdown.disclaimer}</ThemedText>
              </>
            ) : legacyEstimate !== null ? (
              <>
                <View style={styles.priceHeader}>
                  <ThemedText style={styles.priceLabel}>Estimated Value</ThemedText>
                  <View style={styles.priceLiveTag}>
                    <View style={styles.priceLiveDot} />
                    <ThemedText style={styles.priceLiveText}>LIVE RATE</ThemedText>
                  </View>
                </View>
                <ThemedText style={styles.priceValue}>{'\u20B9'} {formatInr(legacyEstimate)}</ThemedText>
                <ThemedText style={styles.priceCalc}>
                  {product.weight}g \u00D7 {'\u20B9'}{formatInr(snap?.published.rate22kt ?? 0)}/10g
                </ThemedText>
                {snap && (
                  <ThemedText style={styles.priceMeta}>
                    Based on today{'\u2019'}s {product.karat === 18 ? '18K' : '22K'} rate \u00B7 Updated {snap.published.atIst} IST
                  </ThemedText>
                )}
                <View style={styles.priceDivider} />
                <ThemedText style={styles.priceDisclaimer}>
                  Final price confirmed at counter based on weight, rate at time of billing, plus GST and making charges.
                </ThemedText>
              </>
            ) : (
              <>
                <ThemedText style={styles.priceValue}>Price on Request</ThemedText>
                <ThemedText style={styles.priceDisclaimer}>
                  Exact weight and purity confirmed from the tag at the counter.
                </ThemedText>
              </>
            )}
          </View>

          {/* ── Action Buttons ── */}
          <View style={styles.actionRow}>
            <Pressable onPress={enquire} style={[styles.actionBtnPrimary, Shadow.sm]} accessibilityLabel="Ask about this design">
              <ThemedText style={styles.actionBtnPrimaryIcon}>{'\u2709'}</ThemedText>
              <ThemedText style={styles.actionBtnPrimaryText}>Ask About This</ThemedText>
            </Pressable>
          </View>
          {has3D && product.threeD?.arEligible && (
            <Pressable onPress={() => router.push('/ar-try-on')} style={[styles.arBtn, Shadow.sm]} accessibilityLabel="Try in AR">
              <ThemedText style={styles.arBtnText}>{'\uD83D\uDCF7'} Try in AR</ThemedText>
              <ThemedText style={styles.arBtnSub}>Point camera at your hand</ThemedText>
            </Pressable>
          )}
          <View style={styles.actionRowSecondary}>
            <Pressable onPress={share} style={[styles.actionBtnSecondary]} accessibilityLabel="Share">
              <ThemedText style={styles.actionBtnSecondaryIcon}>{'\u2197'}</ThemedText>
              <ThemedText style={styles.actionBtnSecondaryText}>Share</ThemedText>
            </Pressable>
            <Pressable onPress={() => router.push('/collections')} style={[styles.actionBtnSecondary]} accessibilityLabel="View Similar">
              <ThemedText style={styles.actionBtnSecondaryIcon}>{'\u25CE'}</ThemedText>
              <ThemedText style={styles.actionBtnSecondaryText}>View Similar</ThemedText>
            </Pressable>
            <Pressable onPress={() => router.push('/store')} style={[styles.actionBtnSecondary]} accessibilityLabel="Visit Store">
              <ThemedText style={styles.actionBtnSecondaryIcon}>{'\u2302'}</ThemedText>
              <ThemedText style={styles.actionBtnSecondaryText}>Visit Store</ThemedText>
            </Pressable>
          </View>

          {/* ── WhatsApp CTA ── */}
          <Pressable onPress={enquire} accessibilityLabel="Enquire on WhatsApp">
            <View style={[styles.ctaWhatsApp, Shadow.sm]}>
              <ThemedText style={styles.ctaWhatsAppText}>
                {'\uD83D\uDCAC'} Enquire on WhatsApp \u2014 {MASTER.phone}
              </ThemedText>
            </View>
          </Pressable>

          {/* ── Stones Detail (3D products) ── */}
          {has3D && product.threeD && product.threeD.stones.length > 0 && (
            <View style={styles.stonesCard}>
              <ThemedText style={styles.stonesTitle}>Stone Details</ThemedText>
              {product.threeD.stones.map((s, i) => (
                <View key={i} style={styles.stoneRow}>
                  <ThemedText style={styles.stoneType}>{s.type}</ThemedText>
                  <ThemedText style={styles.stoneDetail}>
                    {s.count} \u00D7 {s.totalCaratWeight}ct
                    {s.clarity ? ` (${s.clarity})` : ''} \u2022 {s.setting} setting
                  </ThemedText>
                </View>
              ))}
            </View>
          )}

          {/* ── View Similar ── */}
          {similar.length > 0 && (
            <>
              <View style={styles.similarHeader}>
                <ThemedText style={styles.similarTitle}>Similar Designs</ThemedText>
                <ThemedText style={styles.similarCount}>{similar.length} items</ThemedText>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.similarRow}>
                {similar.map((p) => {
                  const simg = imageFor(p);
                  return (
                    <Pressable
                      key={p.id}
                      onPress={() => router.push(`/product/${p.id}`)}
                      style={[styles.similarCard, Shadow.sm]}
                      accessibilityLabel={`Similar ${p.categoryName} ${p.label}`}>
                      {simg ? (
                        <Image source={simg} style={styles.similarImg} resizeMode="contain" />
                      ) : (
                        <View style={[styles.similarImg, { backgroundColor: '#F8F6F3' }]} />
                      )}
                      <View style={styles.similarInfo}>
                        <ThemedText style={styles.similarLabel} numberOfLines={1}>{p.label}</ThemedText>
                        <Pressable onPress={() => {
                          const text = encodeURIComponent(`Namaste ${MASTER.displayName}, please show me designs similar to ${p.label}.`);
                          Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
                        }}>
                          <ThemedText style={styles.similarAsk}>Ask</ThemedText>
                        </Pressable>
                      </View>
                    </Pressable>
                  );
                })}
              </ScrollView>
            </>
          )}

          {/* ── Disclaimer ── */}
          <View style={styles.disclaimer}>
            <ThemedText style={styles.disclaimerText}>
              Hallmarked jewellery. Final price depends on the prevailing rate at the time of billing, plus GST and making charges where applicable.
            </ThemedText>
          </View>
        </ScrollView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFBF5' },
  safeArea: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },

  /* Header */
  headerBar: {
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16,
    paddingVertical: 10, backgroundColor: '#FFFFFF',
    borderBottomWidth: 1, borderBottomColor: '#F0ECE4',
  },
  headerBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#F8F6F3', alignItems: 'center', justifyContent: 'center' },
  headerBtnText: { fontSize: 18, color: '#1A1A2E' },
  headerTitle: { flex: 1, fontSize: 16, fontWeight: '600', color: '#1A1A2E', textAlign: 'center', marginHorizontal: 8 },

  /* Content */
  content: { gap: 16, paddingBottom: Spacing.six },

  /* 3D Viewer */
  viewerCard: {
    marginHorizontal: 16, borderRadius: BorderRadius.xl,
    overflow: 'hidden', backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E5E1D8',
  },
  inspectBar: { padding: 12, borderTopWidth: 1, borderTopColor: '#F0ECE4' },
  inspectLabel: { fontSize: 11, fontWeight: '700', color: '#6B7280', letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 8 },
  hotspotRow: { flexDirection: 'row', gap: 8 },
  hotspotBtn: {
    flex: 1, alignItems: 'center', paddingVertical: 8, borderRadius: 8,
    backgroundColor: '#F8F6F3', borderWidth: 1, borderColor: '#E5E1D8',
  },
  hotspotBtnActive: { backgroundColor: '#23519D', borderColor: '#23519D' },
  hotspotIcon: { fontSize: 16, marginBottom: 2 },
  hotspotLabel: { fontSize: 9, color: '#6B7280', fontWeight: '600' },
  hotspotLabelActive: { color: '#FFFFFF' },

  /* 2D Image */
  imageCard: {
    marginHorizontal: 16, borderRadius: BorderRadius.xl, aspectRatio: 1,
    overflow: 'hidden', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E5E1D8',
  },
  image: { width: '100%', height: '100%' },
  imagePlaceholder: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  imagePlaceholderText: { fontSize: 14, color: '#9CA3AF' },

  /* Info */
  infoSection: { marginHorizontal: 16, gap: 10 },
  infoTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  productCategory: { fontSize: 22, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.3 },
  productLabel: { fontSize: 13, color: '#6B7280', marginTop: 2 },
  heartBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#F8F6F3', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#E5E1D8' },
  heartBtnActive: { backgroundColor: '#FEF2F2', borderColor: '#FECACA' },
  heartIcon: { fontSize: 22, color: '#9CA3AF' },
  heartIconActive: { color: '#DC2626' },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tag: { backgroundColor: '#F8F6F3', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: '#E5E1D8' },
  tagText: { fontSize: 11, fontWeight: '600', color: '#1A1A2E' },
  tagHallmark: { backgroundColor: '#FDF8ED', borderColor: '#E8D9A8' },
  tagHallmarkText: { color: '#A68523' },
  tag3D: { backgroundColor: '#EEF2FF', borderColor: '#C7D2FE' },
  tag3DText: { color: '#4338CA' },

  /* Switcher */
  switcherSection: { marginHorizontal: 16, gap: 12 },
  switcherGroup: { gap: 6 },
  switcherLabel: { fontSize: 11, fontWeight: '700', color: '#6B7280', letterSpacing: 0.5, textTransform: 'uppercase' },
  switcherRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  switcherChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
    backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#E5E1D8',
  },
  switcherChipActive: { borderColor: '#23519D', backgroundColor: '#EEF2FF' },
  colorDot: { width: 12, height: 12, borderRadius: 6 },
  switcherChipText: { fontSize: 12, fontWeight: '500', color: '#6B7280' },
  switcherChipTextActive: { color: '#23519D', fontWeight: '700' },

  /* Price Card */
  priceCard: { marginHorizontal: 16, backgroundColor: '#23519D', borderRadius: BorderRadius.xl, padding: 20, gap: 4 },
  priceHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  priceLabel: { color: '#C9A84C', fontSize: 11, fontWeight: '700', letterSpacing: 1.5, textTransform: 'uppercase' },
  priceLiveTag: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(22,163,74,0.2)', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  priceLiveDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: '#16A34A' },
  priceLiveText: { fontSize: 9, fontWeight: '700', color: '#16A34A', letterSpacing: 1 },
  priceValue: { color: '#FFFFFF', fontSize: 32, fontWeight: '700', letterSpacing: -0.5 },
  priceCalc: { color: 'rgba(255,255,255,0.6)', fontSize: 12 },
  priceMeta: { color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 2 },
  priceDivider: { height: 1, backgroundColor: 'rgba(201,168,76,0.25)', marginVertical: 8 },
  priceDisclaimer: { color: 'rgba(255,255,255,0.6)', fontSize: 11, lineHeight: 15 },

  /* Actions */
  actionRow: { marginHorizontal: 16, gap: 10 },
  actionBtnPrimary: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#23519D', borderRadius: BorderRadius.md, paddingVertical: 14 },
  actionBtnPrimaryIcon: { fontSize: 16, color: '#FFFFFF' },
  actionBtnPrimaryText: { fontSize: 15, fontWeight: '700', color: '#FFFFFF' },
  arBtn: { marginHorizontal: 16, alignItems: 'center', backgroundColor: '#4338CA', borderRadius: BorderRadius.md, paddingVertical: 12 },
  arBtnText: { fontSize: 14, fontWeight: '700', color: '#FFFFFF' },
  arBtnSub: { fontSize: 10, color: 'rgba(255,255,255,0.7)', marginTop: 2 },
  actionRowSecondary: { marginHorizontal: 16, flexDirection: 'row', gap: 10 },
  actionBtnSecondary: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.md, paddingVertical: 12, borderWidth: 1, borderColor: '#E5E1D8' },
  actionBtnSecondaryIcon: { fontSize: 14, color: '#1A1A2E' },
  actionBtnSecondaryText: { fontSize: 12, fontWeight: '600', color: '#1A1A2E' },

  /* WhatsApp CTA */
  ctaWhatsApp: { marginHorizontal: 16, alignItems: 'center', backgroundColor: '#16A34A', borderRadius: BorderRadius.md, paddingVertical: 14 },
  ctaWhatsAppText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },

  /* Stones */
  stonesCard: { marginHorizontal: 16, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, padding: 16, borderWidth: 1, borderColor: '#E5E1D8', gap: 8 },
  stonesTitle: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  stoneRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  stoneType: { fontSize: 13, fontWeight: '600', color: '#1A1A2E', textTransform: 'capitalize' },
  stoneDetail: { fontSize: 12, color: '#6B7280' },

  /* Similar */
  similarHeader: { marginHorizontal: 16, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  similarTitle: { fontSize: 18, fontWeight: '700', color: '#1A1A2E' },
  similarCount: { fontSize: 12, color: '#9CA3AF' },
  similarRow: { paddingHorizontal: 16, gap: 12, paddingBottom: 4 },
  similarCard: { width: 120, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden' },
  similarImg: { width: 120, height: 120 },
  similarInfo: { padding: 8, gap: 2 },
  similarLabel: { fontSize: 11, color: '#1A1A2E', fontWeight: '500' },
  similarAsk: { fontSize: 11, fontWeight: '700', color: '#23519D' },

  /* Disclaimer */
  disclaimer: { marginHorizontal: 16, backgroundColor: '#F8F6F3', borderRadius: BorderRadius.md, padding: 14, borderWidth: 1, borderColor: '#E5E1D8' },
  disclaimerText: { fontSize: 11, color: '#6B7280', lineHeight: 16 },

  /* Not Found */
  notFoundTitle: { fontSize: 20, fontWeight: '700', color: '#1A1A2E' },
  notFoundSub: { fontSize: 13, color: '#6B7280' },
  backBtn: { backgroundColor: '#23519D', borderRadius: 12, paddingHorizontal: 24, paddingVertical: 10, marginTop: 8 },
  backBtnText: { color: '#FFFFFF', fontWeight: '600' },
});
