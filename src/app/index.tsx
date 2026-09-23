import { useRef, useState } from 'react';
import {
  Dimensions,
  FlatList,
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius, Shadow } from '@/constants/theme';
import { useLiveRates } from '@/hooks/use-live-rates';
import { formatInr } from '@/services/rates';
import { byCategory, categories, imageFor, products, heroProducts } from '@/services/products';
import { MASTER, MAPS_URL } from '@/config/master';
import { useCart } from '@/store/cart';
import { useLang, type Lang } from '@/store/lang';
import Category3DCarousel from '@/components/category-3d';

const heroVideoSrc = require('@/assets/aradhana/hero_video.mp4');
const heroAdSrc = require('@/assets/aradhana/hero_ad.mp4');
const heroBridalSrc = require('@/assets/aradhana/hero_bridal.mp4');
const heroBridalStorySrc = require('@/assets/aradhana/hero_bridal_story.mp4');

const heroSlides: { type: 'img' | 'video'; src: number }[] = [
  { type: 'video', src: heroVideoSrc },
  { type: 'video', src: heroAdSrc },
  { type: 'img', src: require('@/assets/aradhana/hero1_discover.jpg') },
  { type: 'video', src: heroBridalSrc },
  { type: 'img', src: require('@/assets/aradhana/hero2_trusted1995.jpg') },
  { type: 'video', src: heroBridalStorySrc },
];

const { width: windowWidth } = Dimensions.get('window');
const PAD = 16;
const CONTENT_MAX = 760;
const HERO_W = Math.min(windowWidth, CONTENT_MAX) - PAD * 2;
const HERO_H = Math.round(HERO_W * 0.55);
const CIRCLE = 108;

const LANG_LABELS: Record<Lang, string> = { en: 'EN', hi: '\u0939\u093F', mr: '\u092E\u0930' };
const LANG_CYCLE: Lang[] = ['en', 'hi', 'mr'];

function SectionHeader({ title, subtitle, onSeeAll }: { title: string; subtitle?: string; onSeeAll?: () => void }) {
  return (
    <View style={styles.sectionHead}>
      <View style={styles.sectionHeadLeft}>
        <ThemedText style={styles.sectionTitle}>{title}</ThemedText>
        {subtitle ? <ThemedText style={styles.sectionSub}>{subtitle}</ThemedText> : null}
      </View>
      {onSeeAll && (
        <Pressable onPress={onSeeAll}>
          <ThemedText style={styles.seeAll}>See All</ThemedText>
        </Pressable>
      )}
    </View>
  );
}

function HeroSlider() {
  const [active, setActive] = useState(0);
  const p0 = useVideoPlayer(heroVideoSrc, (p) => { p.loop = true; p.muted = true; p.play(); });
  const p1 = useVideoPlayer(heroAdSrc, (p) => { p.loop = true; p.muted = true; p.play(); });
  const p3 = useVideoPlayer(heroBridalSrc, (p) => { p.loop = true; p.muted = true; p.play(); });
  const p5 = useVideoPlayer(heroBridalStorySrc, (p) => { p.loop = true; p.muted = true; p.play(); });
  const players = useRef([p0, p1, null, p3, null, p5]);

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const idx = Math.round(e.nativeEvent.contentOffset.x / HERO_W);
    if (idx !== active && idx >= 0 && idx < heroSlides.length) {
      setActive(idx);
    }
  };

  return (
    <View>
      <FlatList
        data={heroSlides}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={32}
        keyExtractor={(_, i) => String(i)}
        renderItem={({ item, index }) => (
          <View style={styles.heroSlideWrap}>
            {item.type === 'video' && players.current[index] ? (
              <VideoView player={players.current[index]!} contentFit="cover" style={styles.heroVideo} />
            ) : (
              <Image source={item.src} style={styles.heroImg} resizeMode="cover" />
            )}
          </View>
        )}
      />
      <View style={styles.dots} pointerEvents="none">
        {heroSlides.map((_, i) => (
          <View key={i} style={[styles.dot, i === active && styles.dotActive]} />
        ))}
      </View>
    </View>
  );
}

export default function HomeScreen() {
  const router = useRouter();
  const scrollRef = useRef<ScrollView>(null);
  const { snap } = useLiveRates();
  const { count } = useCart();
  const { lang, setLang, t } = useLang();

  const cats = categories();
  const showcase = cats.slice(0, 3).map((c) => ({ ...c, photo: byCategory(c.key)[0] }));
  const trending = products.slice(12, 24);

  const curatedCats: { key: string; name: string; img: number }[] = [
    { key: 'bridal', name: 'Bridal', img: require('@/assets/aradhana/cat_bridal.jpg') },
    { key: 'gold', name: 'Gold', img: require('@/assets/aradhana/cat_gold.jpg') },
    { key: 'diamond', name: 'Diamond', img: require('@/assets/aradhana/cat_signature.jpg') },
    { key: 'traditional', name: 'Traditional', img: require('@/assets/aradhana/mid2_favourites.jpg') },
    { key: 'everyday', name: 'Everyday', img: require('@/assets/aradhana/cat_everyday.jpg') },
    { key: 'gifting', name: 'Gifting', img: require('@/assets/aradhana/cat_gifting.jpg') },
    { key: 'investments', name: 'Investments', img: require('@/assets/aradhana/mid3_sip.jpg') },
    { key: 'best_sellers', name: 'Best Sellers', img: require('@/assets/aradhana/hero3_rates.jpg') },
  ];

  const jewelleryWorlds = [
    { id: 'bridal', name: 'Bridal World', desc: 'Complete bridal sets crafted for your most precious moments', heroId: 'HERO-SET-001', gradient: ['#FDF8ED', '#E8D9A8'] },
    { id: 'everyday', name: 'Everyday Gold', desc: 'Elegant daily wear that moves with your life', heroId: 'HERO-BGL-001', gradient: ['#FFFBF5', '#F0ECE4'] },
    { id: 'rings', name: 'Statement Rings', desc: 'Bold designs that speak without words', heroId: 'HERO-RING-003', gradient: ['#EEF2FF', '#C7D2FE'] },
    { id: 'gifting', name: 'Gifting', desc: 'Precious moments, perfectly wrapped', heroId: 'HERO-PEND-001', gradient: ['#FEF2F2', '#FECACA'] },
    { id: 'heritage', name: 'Heritage', desc: 'Timeless designs rooted in tradition', heroId: 'HERO-EARR-001', gradient: ['#FDF8ED', '#E8D9A8'] },
  ];

  const cycleLang = () => {
    const idx = LANG_CYCLE.indexOf(lang);
    setLang(LANG_CYCLE[(idx + 1) % LANG_CYCLE.length]);
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
          <Pressable onPress={() => scrollRef.current?.scrollTo({ y: 0, animated: true })}>
            <View style={styles.headerLeft}>
              <ThemedText style={styles.brandName}>{MASTER.displayName.toUpperCase()}</ThemedText>
              <ThemedText style={styles.brandTag}>{t('purityTrust')}</ThemedText>
            </View>
          </Pressable>
          <View style={styles.headerActions}>
            <Pressable onPress={cycleLang} style={styles.langBtn}>
              <ThemedText style={styles.langText}>{LANG_LABELS[lang]}</ThemedText>
            </Pressable>
            <Pressable onPress={() => router.navigate('/search')} hitSlop={10} style={styles.iconBtn} accessibilityLabel="Search">
              <ThemedText style={styles.iconBtnText}>{'\u2315'}</ThemedText>
            </Pressable>
            <Pressable onPress={() => router.navigate('/cart')} hitSlop={10} style={styles.iconBtn} accessibilityLabel="Cart">
              <ThemedText style={styles.iconBtnText}>{'\uD83D\uDED2'}</ThemedText>
              {count > 0 && (
                <View style={styles.cartBadge}>
                  <ThemedText style={styles.cartBadgeText}>{count}</ThemedText>
                </View>
              )}
            </Pressable>
          </View>
        </View>

        <ScrollView ref={scrollRef} contentContainerStyle={[styles.content, { width: '100%', maxWidth: CONTENT_MAX, alignSelf: 'center' }]} showsVerticalScrollIndicator={false}>

          {/* 3D Category Carousel */}
          <Category3DCarousel
            items={curatedCats}
            onItemPress={() => router.navigate('/collections')}
          />

          {/* Hero Slider */}
          <HeroSlider />

          {/* Jewellery Worlds */}
          <SectionHeader title="Jewellery Worlds" subtitle="Explore curated collections in 3D" />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.worldsContent}>
            {jewelleryWorlds.map((world) => {
              const worldProduct = heroProducts().find(p => p.id === world.heroId);
              return (
                <Pressable
                  key={world.id}
                  onPress={() => router.navigate(`/product/${world.heroId}`)}
                  style={[styles.worldCard, { backgroundColor: world.gradient[0] }, Shadow.sm]}
                  accessibilityLabel={world.name}>
                  <View style={styles.worldInfo}>
                    <ThemedText style={styles.worldName}>{world.name}</ThemedText>
                    <ThemedText style={styles.worldDesc} numberOfLines={2}>{world.desc}</ThemedText>
                    {worldProduct && (
                      <View style={styles.worldTag}>
                        <ThemedText style={styles.worldTagText}>3D Interactive</ThemedText>
                      </View>
                    )}
                  </View>
                  <View style={styles.worldCta}>
                    <ThemedText style={styles.worldCtaText}>Explore {'\u203A'}</ThemedText>
                  </View>
                </Pressable>
              );
            })}
          </ScrollView>

          {/* Live Rate Card */}
          {snap ? (
            <Pressable onPress={() => router.navigate('/gold-rate')} style={[styles.rateCard, Shadow.md]} accessibilityLabel="Live metal rates">
              <View style={styles.rateHeader}>
                <View style={styles.rateHeaderLeft}>
                  <View style={styles.liveIndicator}>
                    <View style={styles.liveDot} />
                    <ThemedText style={styles.liveText}>LIVE</ThemedText>
                  </View>
                  <ThemedText style={styles.rateTime}>{snap.published.atIst.split(', ').pop()}</ThemedText>
                </View>
                <ThemedText style={styles.rateArrow}>{'\u203A'}</ThemedText>
              </View>
              <View style={styles.rateRow}>
                <View style={styles.rateCell}>
                  <ThemedText style={styles.rateLabel}>GOLD 22K</ThemedText>
                  <ThemedText style={styles.rateValue}>{'\u20B9'}{formatInr(snap.published.rate22kt)}</ThemedText>
                  <ThemedText style={styles.rateUnit}>/ 10g</ThemedText>
                </View>
                <View style={styles.rateDivider} />
                <View style={styles.rateCell}>
                  <ThemedText style={styles.rateLabel}>GOLD 24K</ThemedText>
                  <ThemedText style={styles.rateValue}>{'\u20B9'}{formatInr(snap.published.rate24kt)}</ThemedText>
                  <ThemedText style={styles.rateUnit}>/ 10g</ThemedText>
                </View>
                <View style={styles.rateDivider} />
                <View style={styles.rateCell}>
                  <ThemedText style={styles.rateLabel}>SILVER</ThemedText>
                  <ThemedText style={styles.rateValue}>{snap.silver?.published ? `\u20B9${formatInr(snap.silver.published.pure)}` : '--'}</ThemedText>
                  <ThemedText style={styles.rateUnit}>/ kg</ThemedText>
                </View>
              </View>
            </Pressable>
          ) : null}

          {/* Shop By Category */}
          <SectionHeader title={t('shopByCategory')} subtitle={t('exploreCollections')} onSeeAll={() => router.navigate('/collections')} />
          {showcase.map((c) => (
            <Pressable key={c.key} onPress={() => router.navigate('/collections')} style={[styles.showcaseCard, Shadow.sm]} accessibilityLabel={c.name}>
              {c.photo ? (
                <Image source={imageFor(c.photo)} style={styles.showcaseImg} resizeMode="cover" />
              ) : (
                <View style={[styles.showcaseImg, { backgroundColor: '#F8F6F3' }]} />
              )}
              <View style={styles.showcaseOverlay}>
                <ThemedText style={styles.showcaseName}>{c.name}</ThemedText>
                <ThemedText style={styles.showcaseCount}>{c.count} designs</ThemedText>
              </View>
            </Pressable>
          ))}
          <Pressable onPress={() => router.navigate('/collections')} style={styles.outlineBtn} accessibilityLabel="View all collections">
            <ThemedText style={styles.outlineBtnText}>{t('viewAllCollections')}</ThemedText>
          </Pressable>

          {/* New Arrivals */}
          <SectionHeader title={t('newArrivals')} subtitle={t('freshDesigns')} onSeeAll={() => router.navigate('/collections')} />
          <FlatList horizontal showsHorizontalScrollIndicator={false} data={products.slice(0, 12)} keyExtractor={(p) => p.id} contentContainerStyle={styles.railContent}
            renderItem={({ item }) => (
              <Pressable onPress={() => router.navigate(`/product/${item.id}`)} style={[styles.productCard, Shadow.sm]} accessibilityLabel={`${item.categoryName} ${item.label}`}>
                <View style={styles.productImgWrap}><Image source={imageFor(item)} style={styles.productImg} resizeMode="contain" /></View>
                <View style={styles.productInfo}>
                  <ThemedText style={styles.productName} numberOfLines={1}>{item.categoryName}</ThemedText>
                  <ThemedText style={styles.productMeta} numberOfLines={1}>{[item.karat ? `${item.karat}K` : null, item.weight ? `${item.weight.toFixed(2)}g` : null].filter(Boolean).join(' \u00B7 ')}</ThemedText>
                </View>
              </Pressable>
            )} />

          {/* Trending Now */}
          <SectionHeader title={t('trendingNow')} subtitle={t('popularWithCustomers')} />
          <FlatList horizontal showsHorizontalScrollIndicator={false} data={trending} keyExtractor={(p) => p.id} contentContainerStyle={styles.railContent}
            renderItem={({ item }) => (
              <Pressable onPress={() => router.navigate(`/product/${item.id}`)} style={[styles.productCard, Shadow.sm]} accessibilityLabel={`${item.categoryName} ${item.label}`}>
                <View style={styles.productImgWrap}><Image source={imageFor(item)} style={styles.productImg} resizeMode="contain" /></View>
                <View style={styles.productInfo}>
                  <ThemedText style={styles.productName} numberOfLines={1}>{item.categoryName}</ThemedText>
                  <ThemedText style={styles.productMeta} numberOfLines={1}>{[item.karat ? `${item.karat}K` : null, item.weight ? `${item.weight.toFixed(2)}g` : null].filter(Boolean).join(' \u00B7 ')}</ThemedText>
                </View>
              </Pressable>
            )} />

          {/* Hallmarked Section */}
          <View style={[styles.hallmarkCard, Shadow.sm]}>
            <View style={styles.hallmarkLeft}>
              <ThemedText style={styles.hallmarkTitle}>{t('hallmarked916')}</ThemedText>
              <ThemedText style={styles.hallmarkDesc}>{t('hallmarkDesc')}</ThemedText>
            </View>
            <View style={styles.hallmarkBadge}>
              <ThemedText style={styles.hallmarkBadgeText}>916</ThemedText>
            </View>
          </View>

          {/* Visit Us with Map Preview */}
          <SectionHeader title={t('visitShowroom')} subtitle={t('boisaPalghar')} />
          <Pressable style={[styles.visitCard, Shadow.sm]} onPress={() => Linking.openURL(MAPS_URL)} accessibilityLabel="Open in maps">
            <View style={styles.mapPreview}>
              <Image source={{ uri: 'https://tile.openstreetmap.org/17/55482/33960.png' }} style={styles.mapImg} resizeMode="cover" />
              <View style={styles.mapOverlay}>
                <ThemedText style={styles.mapOverlayText}>{'\uD83D\uDCCD'} Open in Maps</ThemedText>
              </View>
            </View>
            <View style={styles.visitInfo}>
              <ThemedText style={styles.visitTitle}>{MASTER.locationDescriptor}</ThemedText>
              <ThemedText style={styles.visitAddr}>{MASTER.addressLines.join(' ')}</ThemedText>
            </View>
          </Pressable>

          {/* Action Buttons Row */}
          <View style={styles.actionRow}>
            <Pressable onPress={() => Linking.openURL(`tel:${MASTER.phone}`)} style={[styles.actionBtn, styles.callBtn, Shadow.sm]}>
              <ThemedText style={styles.actionBtnText}>{'\uD83D\uDCDE'} {t('call')}</ThemedText>
            </Pressable>
            <Pressable onPress={() => { const text = encodeURIComponent(`Namaste ${MASTER.displayName}`); Linking.openURL(`${MASTER.whatsapp}?text=${text}`); }} style={[styles.actionBtn, styles.whatsappBtn, Shadow.sm]}>
              <ThemedText style={[styles.actionBtnText, { color: '#FFFFFF' }]}>{'\uD83D\uDCAC'} {t('whatsapp')}</ThemedText>
            </Pressable>
          </View>

          {/* Social Media */}
          <View style={styles.socialCard}>
            <Pressable onPress={() => Linking.openURL(MASTER.instagram)} style={styles.socialBtn}>
              <ThemedText style={styles.socialIcon}>{'\uD83D\uDCF7'}</ThemedText>
              <ThemedText style={styles.socialText}>Instagram</ThemedText>
              <ThemedText style={styles.socialHandle}>{MASTER.instagramHandle}</ThemedText>
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
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: PAD, paddingVertical: 10, backgroundColor: '#23519D' },
  headerLeft: { gap: 1 },
  brandName: { fontSize: 16, fontWeight: '700', color: '#FFFFFF', letterSpacing: 1.2 },
  brandTag: { fontSize: 9.5, color: '#C9A84C', letterSpacing: 1, textTransform: 'uppercase' },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  langBtn: { backgroundColor: 'rgba(201,168,76,0.25)', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: 'rgba(201,168,76,0.4)' },
  langText: { fontSize: 11, fontWeight: '700', color: '#C9A84C' },
  iconBtn: { width: 42, height: 42, borderRadius: 21, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center', position: 'relative' },
  iconBtnText: { fontSize: 19, color: '#FFFFFF' },
  cartBadge: { position: 'absolute', top: -2, right: -2, backgroundColor: '#C9A84C', borderRadius: 8, minWidth: 16, height: 16, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  cartBadgeText: { color: '#1A1A2E', fontSize: 9, fontWeight: '700' },
  content: { paddingBottom: Spacing.six, gap: 20, paddingTop: 14 },

  /* Jewellery Worlds */
  worldsContent: { paddingHorizontal: PAD, gap: 12 },
  worldCard: {
    width: 200, borderRadius: BorderRadius.xl, padding: 16,
    borderWidth: 1, borderColor: '#E5E1D8', justifyContent: 'space-between',
    minHeight: 140,
  },
  worldInfo: { gap: 6 },
  worldName: { fontSize: 16, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.3 },
  worldDesc: { fontSize: 12, color: '#6B7280', lineHeight: 16 },
  worldTag: { alignSelf: 'flex-start', backgroundColor: 'rgba(35,81,157,0.1)', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, marginTop: 4 },
  worldTagText: { fontSize: 9, fontWeight: '700', color: '#23519D', letterSpacing: 0.5 },
  worldCta: { marginTop: 8 },
  worldCtaText: { fontSize: 13, fontWeight: '700', color: '#23519D' },

  /* 3D Category Carousel */
  categoriesWrap: { paddingVertical: 4 },
  circleRow: { paddingHorizontal: PAD, gap: 18 },
  circle3DWrap: { alignItems: 'center', width: CIRCLE + 16 },
  circle3DOuter: { position: 'relative' },
  circle3DInner: {
    width: CIRCLE, height: CIRCLE, borderRadius: CIRCLE / 2,
    borderWidth: 3, borderColor: '#C9A84C',
    backgroundColor: '#FFFFFF',
    overflow: 'hidden',
    shadowColor: '#000', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.25, shadowRadius: 10,
    elevation: 12,
  },
  circle3DImg: { width: '100%', height: '100%' },
  circle3DShadow: {
    position: 'absolute', bottom: -4, left: '15%', right: '15%', height: 8,
    backgroundColor: 'rgba(0,0,0,0.18)', borderRadius: 40,
  },
  circle3DLabel: { fontSize: 11, fontWeight: '600', color: '#1A1A2E', marginTop: 10, maxWidth: CIRCLE + 16, textAlign: 'center', lineHeight: 14 },

  heroSlideWrap: { width: HERO_W, borderRadius: BorderRadius.lg, overflow: 'hidden' },
  heroImg: { width: '100%', height: HERO_H },
  heroVideo: { width: '100%', height: HERO_H, backgroundColor: '#1A1A2E' },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 10 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#E5E1D8' },
  dotActive: { backgroundColor: '#C9A84C', width: 24 },
  rateCard: { backgroundColor: '#FFFFFF', borderRadius: BorderRadius.xl, marginHorizontal: PAD, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden' },
  rateHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8 },
  rateHeaderLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  liveIndicator: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#16A34A' },
  liveText: { fontSize: 10, fontWeight: '700', color: '#16A34A', letterSpacing: 1 },
  rateTime: { fontSize: 11, color: '#9CA3AF' },
  rateArrow: { fontSize: 22, color: '#C9A84C', fontWeight: '600' },
  rateRow: { flexDirection: 'row', alignItems: 'center', paddingBottom: 14, paddingHorizontal: 12 },
  rateCell: { flex: 1, alignItems: 'center', gap: 2 },
  rateLabel: { fontSize: 10, color: '#6B7280', letterSpacing: 0.5, fontWeight: '600' },
  rateValue: { fontSize: 15, fontWeight: '700', color: '#23519D' },
  rateUnit: { fontSize: 9, color: '#9CA3AF' },
  rateDivider: { width: 1, height: 28, backgroundColor: '#F0ECE4' },
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: PAD },
  sectionHeadLeft: { gap: 2 },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.3 },
  sectionSub: { fontSize: 12, color: '#9CA3AF' },
  seeAll: { fontSize: 13, fontWeight: '600', color: '#23519D' },
  showcaseCard: { marginHorizontal: PAD, borderRadius: BorderRadius.lg, overflow: 'hidden', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E5E1D8' },
  showcaseImg: { width: '100%', height: Math.round(HERO_W * 0.5) },
  showcaseOverlay: { position: 'absolute', left: 14, bottom: 14, backgroundColor: 'rgba(255,255,255,0.95)', borderRadius: BorderRadius.md, paddingHorizontal: 14, paddingVertical: 8 },
  showcaseName: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  showcaseCount: { fontSize: 11, color: '#C9A84C', fontWeight: '600', marginTop: 1 },
  outlineBtn: { alignSelf: 'center', borderWidth: 1.5, borderColor: '#23519D', borderRadius: BorderRadius.md, paddingHorizontal: 24, paddingVertical: 10 },
  outlineBtnText: { fontSize: 13, fontWeight: '700', color: '#23519D', letterSpacing: 0.3 },
  railContent: { paddingHorizontal: PAD, gap: 12 },
  productCard: { width: 150, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden' },
  productImgWrap: { width: '100%', aspectRatio: 1, backgroundColor: '#FFFBF5' },
  productImg: { width: '100%', height: '100%' },
  productInfo: { padding: 10, gap: 2 },
  productName: { fontSize: 12, fontWeight: '600', color: '#1A1A2E' },
  productMeta: { fontSize: 11, color: '#9CA3AF' },
  hallmarkCard: { marginHorizontal: PAD, flexDirection: 'row', alignItems: 'center', backgroundColor: '#FDF8ED', borderRadius: BorderRadius.lg, padding: 16, borderWidth: 1, borderColor: '#E8D9A8', gap: 12 },
  hallmarkLeft: { flex: 1, gap: 4 },
  hallmarkTitle: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  hallmarkDesc: { fontSize: 12, color: '#6B7280', lineHeight: 16 },
  hallmarkBadge: { width: 56, height: 56, borderRadius: 28, backgroundColor: '#C9A84C', alignItems: 'center', justifyContent: 'center' },
  hallmarkBadgeText: { fontSize: 18, fontWeight: '800', color: '#FFFFFF' },
  visitCard: { marginHorizontal: PAD, borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', backgroundColor: '#FFFFFF', overflow: 'hidden' },
  mapPreview: { width: '100%', height: 140, backgroundColor: '#E8EFFA' },
  mapImg: { width: '100%', height: '100%' },
  mapOverlay: { position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(35,81,157,0.85)', paddingVertical: 8, alignItems: 'center' },
  mapOverlayText: { color: '#FFFFFF', fontSize: 13, fontWeight: '600' },
  visitInfo: { padding: 14, gap: 4 },
  visitTitle: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  visitAddr: { fontSize: 12, color: '#6B7280', lineHeight: 16 },
  actionRow: { marginHorizontal: PAD, flexDirection: 'row', gap: 10 },
  actionBtn: { flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: BorderRadius.md },
  callBtn: { backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#23519D' },
  whatsappBtn: { backgroundColor: '#16A34A' },
  actionBtnText: { fontSize: 14, fontWeight: '700', color: '#23519D' },
  socialCard: { marginHorizontal: PAD, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden' },
  socialBtn: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10 },
  socialIcon: { fontSize: 22 },
  socialText: { fontSize: 14, fontWeight: '600', color: '#1A1A2E', flex: 1 },
  socialHandle: { fontSize: 12, color: '#9CA3AF' },
});
