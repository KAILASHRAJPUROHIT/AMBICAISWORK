/* eslint-disable react-hooks/immutability */
import { useEffect, useRef, useState, useCallback } from 'react';
import {
  Dimensions,
  FlatList,
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withRepeat,
  withSequence,
  interpolate,
  Extrapolation,
  useAnimatedScrollHandler,
  runOnJS,
  type SharedValue,
} from 'react-native-reanimated';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, BorderRadius, Shadow } from '@/constants/theme';
import { useLiveRates } from '@/hooks/use-live-rates';
import { formatInr } from '@/services/rates';
import { byCategory, categories, imageFor, products } from '@/services/products';
import { MASTER, MAPS_URL } from '@/config/master';
import { useCart } from '@/store/cart';
import { useLang, type Lang } from '@/store/lang';
import Category3DCarousel from '@/components/category-3d';
import { SPRING, TIMING, Floating, useSlideReveal } from '@/components/animated-3d';
import { Button3D } from '@/components/ui-3d';

const AnimatedView = Animated.View;

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
const HERO_H = Math.round(HERO_W * 0.65);

const LANG_LABELS: Record<Lang, string> = { en: 'EN', hi: '\u0939\u093F', mr: '\u092E\u0930' };
const LANG_CYCLE: Lang[] = ['en', 'hi', 'mr'];

/* ═══════════════════════════════════════════════════════════
   3D SECTION HEADER — Animated reveal on mount
   ═══════════════════════════════════════════════════════════ */
function SectionHeader3D({ title, subtitle, onSeeAll, delay = 0 }: {
  title: string; subtitle?: string; onSeeAll?: () => void; delay?: number;
}) {
  const reveal = useSlideReveal('up', delay);

  return (
    <AnimatedView style={[reveal.animatedStyle, styles.sectionHead]}>
      <View style={styles.sectionHeadLeft}>
        <ThemedText style={styles.sectionTitle}>{title}</ThemedText>
        {subtitle ? <ThemedText style={styles.sectionSub}>{subtitle}</ThemedText> : null}
      </View>
      {onSeeAll && (
        <Pressable onPress={onSeeAll}>
          <ThemedText style={styles.seeAll}>See All</ThemedText>
        </Pressable>
      )}
    </AnimatedView>
  );
}

/* ═══════════════════════════════════════════════════════════
   3D HERO SLIDER — Depth parallax on scroll
   ═══════════════════════════════════════════════════════════ */
function HeroSlider3D() {
  const [active, setActive] = useState(0);
  const scrollX = useSharedValue(0);
  const player0 = useVideoPlayer(active === 0 ? heroVideoSrc : heroVideoSrc, (p) => { p.loop = true; p.muted = true; });
  const player1 = useVideoPlayer(active === 1 ? heroAdSrc : heroVideoSrc, (p) => { p.loop = true; p.muted = true; });
  const player3 = useVideoPlayer(active === 3 ? heroBridalSrc : heroVideoSrc, (p) => { p.loop = true; p.muted = true; });
  const player5 = useVideoPlayer(active === 5 ? heroBridalStorySrc : heroVideoSrc, (p) => { p.loop = true; p.muted = true; });

  useEffect(() => {
    const all = [player0, player1, player3, player5];
    all.forEach((p, i) => {
      const slideIdx = [0, 1, 3, 5][i];
      if (slideIdx === active) {
        try { p.play(); } catch {}
      } else {
        try { p.pause(); } catch {}
      }
    });
  }, [active, player0, player1, player3, player5]);

  const players = useRef([player0, player1, null, player3, null, player5]);

  const setActiveIndex = useCallback((idx: number) => {
    setActive(idx);
  }, []);

  const onScroll = useAnimatedScrollHandler({
    onScroll: (e) => {
      scrollX.value = e.contentOffset.x;
      const idx = Math.round(e.contentOffset.x / HERO_W);
      if (idx >= 0 && idx < heroSlides.length) {
        runOnJS(setActiveIndex)(idx);
      }
    },
  });

  return (
    <View>
      <Animated.ScrollView
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.heroScrollContent}
      >
        {heroSlides.map((item, i) => (
          <HeroSlide3D key={i} item={item} index={i} scrollX={scrollX} players={players} />
        ))}
      </Animated.ScrollView>
      <View style={styles.dots} pointerEvents="none">
        {heroSlides.map((_, i) => (
          <AnimatedDot key={i} index={i} activeIndex={active} />
        ))}
      </View>
    </View>
  );
}

function HeroSlide3D({ item, index, scrollX, players }: {
  item: { type: 'img' | 'video'; src: number };
  index: number;
  scrollX: SharedValue<number>;
  players: React.MutableRefObject<(any | null)[]>;
}) {
  const animStyle = useAnimatedStyle(() => {
    const diff = (index * HERO_W - scrollX.value) / HERO_W;
    const absDiff = Math.abs(diff);
    const scale = interpolate(absDiff, [0, 0.5, 1], [1, 0.92, 0.85], Extrapolation.CLAMP);
    const opacity = interpolate(absDiff, [0, 0.5, 1], [1, 0.8, 0.4], Extrapolation.CLAMP);
    const rotateY = interpolate(diff, [-1, 0, 1], [-8, 0, 8], Extrapolation.CLAMP);

    return {
      transform: [
        { perspective: 1000 },
        { scale },
        { rotateY: `${rotateY}deg` },
      ],
      opacity,
    };
  }, [index]);

  return (
    <Animated.View style={[styles.heroSlideWrap, animStyle]}>
      {item.type === 'video' && players.current[index] ? (
        <VideoView player={players.current[index]!} contentFit="cover" style={styles.heroVideo} />
      ) : (
        <Image source={item.src} style={styles.heroImg} resizeMode="cover" />
      )}
    </Animated.View>
  );
}

function AnimatedDot({ index, activeIndex }: { index: number; activeIndex: number }) {
  const isActive = index === activeIndex;
  const scale = useSharedValue(isActive ? 1 : 0.8);
  const width = useSharedValue(isActive ? 24 : 8);

  useEffect(() => {
    if (isActive) {
      scale.value = withSpring(1, SPRING.bouncy);
      width.value = withTiming(24, { duration: TIMING.fast });
    } else {
      scale.value = withSpring(0.8, SPRING.snappy);
      width.value = withTiming(8, { duration: TIMING.fast });
    }
  }, [isActive, scale, width]);

  const animStyle = useAnimatedStyle(() => ({
    width: width.value,
    transform: [{ scale: scale.value }],
  }));

  return (
    <Animated.View
      style={[
        styles.dot,
        index === activeIndex && styles.dotActive,
        animStyle,
      ]}
    />
  );
}

/* ═══════════════════════════════════════════════════════════
   3D JEWELLERY WORLD CARD — Tilt + glow on press
   ═══════════════════════════════════════════════════════════ */
function WorldCard3D({ world, onPress }: { world: any; onPress: () => void }) {
  const scale = useSharedValue(1);
  const rotateX = useSharedValue(0);
  const rotateY = useSharedValue(0);
  const elevation = useSharedValue(2);
  const glowOpacity = useSharedValue(0);

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { perspective: 800 },
      { scale: scale.value },
      { rotateX: `${rotateX.value}deg` },
      { rotateY: `${rotateY.value}deg` },
    ],
    elevation: elevation.value,
    shadowOpacity: interpolate(glowOpacity.value, [0, 1], [0.05, 0.25], Extrapolation.CLAMP),
  }));

  const glowStyle = useAnimatedStyle(() => ({
    shadowColor: '#C9A84C',
    shadowRadius: interpolate(glowOpacity.value, [0, 1], [0, 16], Extrapolation.CLAMP),
  }));

  const onGrant = useCallback(() => {
    scale.value = withSpring(0.97, SPRING.snappy);
    elevation.value = withSpring(8, SPRING.gentle);
    glowOpacity.value = withTiming(1, { duration: TIMING.normal });
  }, [scale, elevation, glowOpacity]);

  const onMove = useCallback((evt: any) => {
    const { locationX, locationY } = evt.nativeEvent;
    const x = (locationX - 80) / 80;
    const y = (locationY - 70) / 70;
    rotateY.value = withSpring(x * 8, SPRING.gentle);
    rotateX.value = withSpring(-y * 8, SPRING.gentle);
  }, [rotateX, rotateY]);

  const onRelease = useCallback(() => {
    scale.value = withSpring(1, SPRING.bouncy);
    rotateX.value = withSpring(0, SPRING.snappy);
    rotateY.value = withSpring(0, SPRING.snappy);
    elevation.value = withSpring(2, SPRING.gentle);
    glowOpacity.value = withTiming(0, { duration: TIMING.normal });
  }, [scale, rotateX, rotateY, elevation, glowOpacity]);

  return (
    <Pressable
      onPress={onPress}
      onPressIn={onGrant}
      onPressMove={onMove}
      onPressOut={onRelease}
      accessibilityLabel={world.name}>
      <Animated.View style={[styles.worldCard, { backgroundColor: world.gradient[0] }, animStyle, glowStyle]}>
        <View style={styles.worldInfo}>
          <ThemedText style={styles.worldName}>{world.name}</ThemedText>
          <ThemedText style={styles.worldDesc} numberOfLines={2}>{world.desc}</ThemedText>
          <View style={styles.worldTag}>
            <ThemedText style={styles.worldTagText}>3D Interactive</ThemedText>
          </View>
        </View>
        <View style={styles.worldCta}>
          <ThemedText style={styles.worldCtaText}>Explore {'\u203A'}</ThemedText>
        </View>
      </Animated.View>
    </Pressable>
  );
}

/* ═══════════════════════════════════════════════════════════
   3D LIVE RATE CARD — Pulsing glow + animated values
   ═══════════════════════════════════════════════════════════ */
function RateCard3D({ snap, onPress }: { snap: any; onPress: () => void }) {
  const scale = useSharedValue(1);
  const glowPulse = useSharedValue(0);

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const glowStyle = useAnimatedStyle(() => ({
    shadowColor: '#16A34A',
    shadowOpacity: interpolate(glowPulse.value, [0, 1], [0.08, 0.2], Extrapolation.CLAMP),
    shadowRadius: interpolate(glowPulse.value, [0, 1], [4, 12], Extrapolation.CLAMP),
  }));

  useEffect(() => {
    glowPulse.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 1500 }),
        withTiming(0, { duration: 1500 }),
      ),
      -1,
      true,
    );
  }, [glowPulse]);

  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => { scale.value = withSpring(0.98, SPRING.snappy); }}
      onPressOut={() => { scale.value = withSpring(1, SPRING.bouncy); }}
      accessibilityLabel="Live metal rates">
      <Animated.View style={[styles.rateCard, Shadow.md, animStyle, glowStyle]}>
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
      </Animated.View>
    </Pressable>
  );
}

/* ═══════════════════════════════════════════════════════════
   3D PRODUCT CARD — For horizontal rails
   ═══════════════════════════════════════════════════════════ */
function ProductCard3D({ item, onPress }: { item: any; onPress: () => void }) {
  const scale = useSharedValue(1);
  const rotateY = useSharedValue(0);
  const shimmerX = useSharedValue(-100);

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { perspective: 800 },
      { scale: scale.value },
      { rotateY: `${rotateY.value}deg` },
    ],
  }));

  const shimmerStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: shimmerX.value }],
  }));

  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => {
        scale.value = withSpring(0.96, SPRING.snappy);
        shimmerX.value = withTiming(200, { duration: 500 });
      }}
      onPressOut={() => {
        scale.value = withSpring(1, SPRING.bouncy);
        rotateY.value = withSpring(0, SPRING.snappy);
        shimmerX.value = withTiming(-100, { duration: 0 });
      }}
      onPressMove={(evt) => {
        const { locationX } = evt.nativeEvent;
        const x = (locationX - 75) / 75;
        rotateY.value = withSpring(x * 6, SPRING.gentle);
      }}
      accessibilityLabel={`${item.categoryName} ${item.label}`}>
      <Animated.View style={[styles.productCard, Shadow.sm, animStyle]}>
        <View style={styles.productImgWrap}>
          <Image source={imageFor(item)} style={styles.productImg} resizeMode="contain" />
          <Animated.View style={[styles.productShimmer, shimmerStyle]} />
        </View>
        <View style={styles.productInfo}>
          <ThemedText style={styles.productName} numberOfLines={1}>{item.categoryName}</ThemedText>
          <ThemedText style={styles.productMeta} numberOfLines={1}>
            {[item.karat ? `${item.karat}K` : null, item.weight ? `${item.weight.toFixed(2)}g` : null].filter(Boolean).join(' \u00B7 ')}
          </ThemedText>
        </View>
      </Animated.View>
    </Pressable>
  );
}

/* ═══════════════════════════════════════════════════════════
   3D SHOWCASE CARD — Category showcase with depth
   ═══════════════════════════════════════════════════════════ */
function ShowcaseCard3D({ c, onPress }: { c: any; onPress: () => void }) {
  const scale = useSharedValue(1);
  const elevation = useSharedValue(2);

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    elevation: elevation.value,
    shadowOpacity: interpolate(elevation.value, [0, 10], [0.05, 0.2], Extrapolation.CLAMP),
  }));

  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => {
        scale.value = withSpring(0.98, SPRING.snappy);
        elevation.value = withSpring(8, SPRING.gentle);
      }}
      onPressOut={() => {
        scale.value = withSpring(1, SPRING.bouncy);
        elevation.value = withSpring(2, SPRING.gentle);
      }}
      accessibilityLabel={c.name}>
      <Animated.View style={[styles.showcaseCard, Shadow.sm, animStyle]}>
        {c.photo ? (
          <Image source={imageFor(c.photo)} style={styles.showcaseImg} resizeMode="cover" />
        ) : (
          <View style={[styles.showcaseImg, { backgroundColor: '#F8F6F3' }]} />
        )}
        <View style={styles.showcaseOverlay}>
          <ThemedText style={styles.showcaseName}>{c.name}</ThemedText>
          <ThemedText style={styles.showcaseCount}>{c.count} designs</ThemedText>
        </View>
      </Animated.View>
    </Pressable>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN HOME SCREEN
   ═══════════════════════════════════════════════════════════ */
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

          {/* 3D Hero Slider */}
          <HeroSlider3D />

          {/* Jewellery Worlds — 3D Cards */}
          <SectionHeader3D title="Jewellery Worlds" subtitle="Explore curated collections in 3D" delay={100} />
          <View style={styles.worldsGrid}>
            {jewelleryWorlds.map((world) => (
              <WorldCard3D
                key={world.id}
                world={world}
                onPress={() => router.push(`/product/${world.heroId}`)}
              />
            ))}
          </View>

          {/* 3D Live Rate Card */}
          {snap ? <RateCard3D snap={snap} onPress={() => router.navigate('/gold-rate')} /> : null}

          {/* Shop By Category — 3D Showcase Cards */}
          <SectionHeader3D title={t('shopByCategory')} subtitle={t('exploreCollections')} onSeeAll={() => router.navigate('/collections')} delay={200} />
          {showcase.map((c) => (
            <ShowcaseCard3D key={c.key} c={c} onPress={() => router.navigate('/collections')} />
          ))}
          <Button3D variant="secondary" size="sm" onPress={() => router.navigate('/collections')} style={styles.outlineBtn3D}>
            {t('viewAllCollections')}
          </Button3D>

          {/* New Arrivals — 3D Product Cards */}
          <SectionHeader3D title={t('newArrivals')} subtitle={t('freshDesigns')} onSeeAll={() => router.navigate('/collections')} delay={300} />
          <FlatList horizontal showsHorizontalScrollIndicator={false} data={products.slice(0, 12)} keyExtractor={(p) => p.id} contentContainerStyle={styles.railContent}
            renderItem={({ item }) => (
              <ProductCard3D item={item} onPress={() => router.navigate(`/product/${item.id}`)} />
            )} />

          {/* Trending Now — 3D Product Cards */}
          <SectionHeader3D title={t('trendingNow')} subtitle={t('popularWithCustomers')} delay={400} />
          <FlatList horizontal showsHorizontalScrollIndicator={false} data={trending} keyExtractor={(p) => p.id} contentContainerStyle={styles.railContent}
            renderItem={({ item }) => (
              <ProductCard3D item={item} onPress={() => router.navigate(`/product/${item.id}`)} />
            )} />

          {/* Hallmarked Section — 3D Card */}
          <Floating amplitude={3} speed={4000}>
            <View style={[styles.hallmarkCard, Shadow.sm]}>
              <View style={styles.hallmarkLeft}>
                <ThemedText style={styles.hallmarkTitle}>{t('hallmarked916')}</ThemedText>
                <ThemedText style={styles.hallmarkDesc}>{t('hallmarkDesc')}</ThemedText>
              </View>
              <View style={styles.hallmarkBadge}>
                <ThemedText style={styles.hallmarkBadgeText}>916</ThemedText>
              </View>
            </View>
          </Floating>

          {/* Visit Us with Map Preview */}
          <SectionHeader3D title={t('visitShowroom')} subtitle={t('boisaPalghar')} delay={500} />
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

          {/* 3D Action Buttons */}
          <View style={styles.actionRow}>
            <Button3D variant="secondary" onPress={() => Linking.openURL(`tel:${MASTER.phone}`)} style={{ flex: 1 }}>
              {'\uD83D\uDCDE'} {t('call')}
            </Button3D>
            <Button3D
              variant="primary"
              onPress={() => {
                const text = encodeURIComponent(`Namaste ${MASTER.displayName}`);
                Linking.openURL(`${MASTER.whatsapp}?text=${text}`);
              }}
              style={{ flex: 1 }}>
              {'\uD83D\uDCAC'} {t('whatsapp')}
            </Button3D>
          </View>

          {/* Social Media — 3D Card */}
          <Pressable onPress={() => Linking.openURL(MASTER.instagram)} style={styles.socialCard}>
            <View style={styles.socialBtn}>
              <ThemedText style={styles.socialIcon}>{'\uD83D\uDCF7'}</ThemedText>
              <ThemedText style={styles.socialText}>Instagram</ThemedText>
              <ThemedText style={styles.socialHandle}>{MASTER.instagramHandle}</ThemedText>
            </View>
          </Pressable>

          <View style={{ height: 20 }} />
        </ScrollView>
      </SafeAreaView>
    </ThemedView>
  );
}

/* ═══════════════════════════════════════════════════════════
   STYLES
   ═══════════════════════════════════════════════════════════ */
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

  /* Hero */
  heroScrollContent: { paddingLeft: PAD, paddingRight: PAD },
  heroSlideWrap: { width: HERO_W, borderRadius: BorderRadius.lg, overflow: 'hidden', marginRight: 0 },
  heroImg: { width: '100%', height: HERO_H },
  heroVideo: { width: '100%', height: HERO_H, backgroundColor: '#1A1A2E' },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 10 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#E5E1D8' },
  dotActive: { backgroundColor: '#C9A84C', width: 24 },

  /* Jewellery Worlds */
  worldsGrid: { gap: 12, paddingHorizontal: PAD },
  worldCard: {
    width: '100%', borderRadius: BorderRadius.xl, padding: 18,
    borderWidth: 1, borderColor: '#E5E1D8', justifyContent: 'space-between',
    minHeight: 130,
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowRadius: 10,
  },
  worldInfo: { gap: 6 },
  worldName: { fontSize: 16, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.3 },
  worldDesc: { fontSize: 12, color: '#6B7280', lineHeight: 16 },
  worldTag: { alignSelf: 'flex-start', backgroundColor: 'rgba(35,81,157,0.1)', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, marginTop: 4 },
  worldTagText: { fontSize: 9, fontWeight: '700', color: '#23519D', letterSpacing: 0.5 },
  worldCta: { marginTop: 8 },
  worldCtaText: { fontSize: 13, fontWeight: '700', color: '#23519D' },

  /* Rate Card */
  rateCard: { borderRadius: BorderRadius.xl, marginHorizontal: PAD, overflow: 'hidden', shadowColor: '#000', shadowOffset: { width: 0, height: 6 }, backgroundColor: '#1A1A2E' },
  rateHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8 },
  rateHeaderLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  liveIndicator: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#16A34A' },
  liveText: { fontSize: 10, fontWeight: '700', color: '#4ADE80', letterSpacing: 1 },
  rateTime: { fontSize: 11, color: 'rgba(255,255,255,0.5)' },
  rateArrow: { fontSize: 22, color: '#C9A84C', fontWeight: '600' },
  rateRow: { flexDirection: 'row', alignItems: 'center', paddingBottom: 14, paddingHorizontal: 12 },
  rateCell: { flex: 1, alignItems: 'center', gap: 2 },
  rateLabel: { fontSize: 10, color: 'rgba(255,255,255,0.6)', letterSpacing: 0.5, fontWeight: '600' },
  rateValue: { fontSize: 16, fontWeight: '700', color: '#FFFFFF' },
  rateUnit: { fontSize: 9, color: 'rgba(255,255,255,0.4)' },
  rateDivider: { width: 1, height: 30, backgroundColor: 'rgba(255,255,255,0.12)' },

  /* Section Headers */
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: PAD },
  sectionHeadLeft: { gap: 2 },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: '#1A1A2E', letterSpacing: -0.3 },
  sectionSub: { fontSize: 12, color: '#9CA3AF' },
  seeAll: { fontSize: 13, fontWeight: '600', color: '#23519D' },

  /* Showcase */
  showcaseCard: { marginHorizontal: PAD, borderRadius: BorderRadius.lg, overflow: 'hidden', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E5E1D8' },
  showcaseImg: { width: '100%', height: Math.round(HERO_W * 0.55) },
  showcaseOverlay: { position: 'absolute', left: 14, bottom: 14, backgroundColor: 'rgba(255,255,255,0.95)', borderRadius: BorderRadius.md, paddingHorizontal: 14, paddingVertical: 8 },
  showcaseName: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  showcaseCount: { fontSize: 11, color: '#C9A84C', fontWeight: '600', marginTop: 1 },
  outlineBtn3D: { alignSelf: 'center' },

  /* Product Cards */
  railContent: { paddingHorizontal: PAD, gap: 14 },
  productCard: { width: 170, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden', shadowColor: '#000', shadowOffset: { width: 0, height: 3 } },
  productImgWrap: { width: '100%', aspectRatio: 1, backgroundColor: '#FFFBF5', position: 'relative', overflow: 'hidden' },
  productImg: { width: '100%', height: '100%' },
  productShimmer: { position: 'absolute', top: 0, left: 0, width: 40, height: '100%', backgroundColor: 'rgba(255,255,255,0.4)', transform: [{ skewX: '-20deg' }] },
  productInfo: { padding: 10, gap: 2 },
  productName: { fontSize: 12, fontWeight: '600', color: '#1A1A2E' },
  productMeta: { fontSize: 11, color: '#9CA3AF' },

  /* Hallmark */
  hallmarkCard: { marginHorizontal: PAD, flexDirection: 'row', alignItems: 'center', backgroundColor: '#FDF8ED', borderRadius: BorderRadius.lg, padding: 16, borderWidth: 1, borderColor: '#E8D9A8', gap: 12 },
  hallmarkLeft: { flex: 1, gap: 4 },
  hallmarkTitle: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  hallmarkDesc: { fontSize: 12, color: '#6B7280', lineHeight: 16 },
  hallmarkBadge: { width: 56, height: 56, borderRadius: 28, backgroundColor: '#C9A84C', alignItems: 'center', justifyContent: 'center' },
  hallmarkBadgeText: { fontSize: 18, fontWeight: '800', color: '#FFFFFF' },

  /* Visit */
  visitCard: { marginHorizontal: PAD, borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', backgroundColor: '#FFFFFF', overflow: 'hidden' },
  mapPreview: { width: '100%', height: 140, backgroundColor: '#E8EFFA' },
  mapImg: { width: '100%', height: '100%' },
  mapOverlay: { position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(35,81,157,0.85)', paddingVertical: 8, alignItems: 'center' },
  mapOverlayText: { color: '#FFFFFF', fontSize: 13, fontWeight: '600' },
  visitInfo: { padding: 14, gap: 4 },
  visitTitle: { fontSize: 14, fontWeight: '700', color: '#1A1A2E' },
  visitAddr: { fontSize: 12, color: '#6B7280', lineHeight: 16 },

  /* Actions */
  actionRow: { marginHorizontal: PAD, flexDirection: 'row', gap: 10 },

  /* Social */
  socialCard: { marginHorizontal: PAD, backgroundColor: '#FFFFFF', borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: '#E5E1D8', overflow: 'hidden' },
  socialBtn: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10 },
  socialIcon: { fontSize: 22 },
  socialText: { fontSize: 14, fontWeight: '600', color: '#1A1A2E', flex: 1 },
  socialHandle: { fontSize: 12, color: '#9CA3AF' },
});
