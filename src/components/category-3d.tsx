import { useCallback } from 'react';
import { StyleSheet, View, useWindowDimensions, Image, Pressable } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  useAnimatedScrollHandler,
  type SharedValue,
} from 'react-native-reanimated';
import { ThemedText } from '@/components/themed-text';

const ITEM_W = 100;
const GAP = 14;
const STRIDE = ITEM_W + GAP;

interface Props {
  items: { key: string; name: string; img: number }[];
  onItemPress: (key: string) => void;
}

export default function Category3DCarousel({ items, onItemPress }: Props) {
  const { width } = useWindowDimensions();
  const scrollX = useSharedValue(0);
  const totalW = items.length * STRIDE;
  const pad = Math.round((width - ITEM_W) / 2);

  const onScroll = useAnimatedScrollHandler({
    onScroll: (e) => {
      scrollX.value = e.contentOffset.x;
    },
  });

  const handlePress = useCallback((key: string) => {
    onItemPress(key);
  }, [onItemPress]);

  return (
    <View style={styles.container}>
      <Animated.ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        snapToInterval={STRIDE}
        decelerationRate="fast"
        contentContainerStyle={{ width: totalW + pad * 2, paddingHorizontal: pad }}
        onScroll={onScroll}
        scrollEventThrottle={16}
      >
        {items.map((item, i) => (
          <CategoryItem
            key={item.key}
            item={item}
            index={i}
            scrollX={scrollX}
            screenWidth={width}
            onPress={handlePress}
          />
        ))}
      </Animated.ScrollView>
      <View style={styles.indicatorRow} pointerEvents="none">
        <ThemedText style={styles.hint}>{'\u2190'} swipe {'\u2192'}</ThemedText>
      </View>
    </View>
  );
}

function CategoryItem({ item, index, scrollX, screenWidth, onPress }: {
  item: { key: string; name: string; img: number };
  index: number;
  scrollX: SharedValue<number>;
  screenWidth: number;
  onPress: (key: string) => void;
}) {
  const animatedStyle = useAnimatedStyle(() => {
    const itemScreenPos = index * STRIDE - scrollX.value;
    const center = screenWidth / 2 - ITEM_W / 2;
    const diff = (itemScreenPos - center) / STRIDE;
    const absDiff = Math.abs(diff);
    const isCenter = absDiff < 0.4;

    const scale = isCenter ? 1.15 : Math.max(0.68, 1 - absDiff * 0.12);
    const rotateY = Math.max(-18, Math.min(18, diff * -10));
    const opacity = isCenter ? 1 : Math.max(0.4, 1 - absDiff * 0.18);
    const zIndex = isCenter ? 100 : Math.round(50 - absDiff * 6);

    return {
      transform: [
        { perspective: 600 },
        { scale },
        { rotateY: `${rotateY}deg` },
      ],
      opacity,
      zIndex,
    };
  }, [index, screenWidth]);

  const cardStyle = useAnimatedStyle(() => {
    const itemScreenPos = index * STRIDE - scrollX.value;
    const center = screenWidth / 2 - ITEM_W / 2;
    const diff = (itemScreenPos - center) / STRIDE;
    const absDiff = Math.abs(diff);
    const isCenter = absDiff < 0.4;

    return {
      borderColor: isCenter ? '#C9A84C' : 'rgba(201,168,76,0.3)',
      borderWidth: isCenter ? 3.5 : 1.5,
      shadowOpacity: isCenter ? 0.5 : 0.08,
      elevation: isCenter ? 18 : 3,
    };
  }, [index, screenWidth]);

  return (
    <Animated.View style={[styles.itemWrap, animatedStyle]}>
      <Pressable onPress={() => onPress(item.key)}>
        <Animated.View style={[styles.card, cardStyle]}>
          <Image source={item.img} style={styles.cardImg} resizeMode="cover" />
        </Animated.View>
        <ThemedText style={styles.label} numberOfLines={1}>{item.name}</ThemedText>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    height: 180,
    overflow: 'hidden',
  },
  itemWrap: {
    width: ITEM_W,
    alignItems: 'center',
    marginRight: GAP,
  },
  card: {
    width: ITEM_W,
    height: ITEM_W,
    borderRadius: ITEM_W / 2,
    backgroundColor: '#FFFFFF',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 12,
  },
  cardImg: {
    width: '100%',
    height: '100%',
  },
  label: {
    fontSize: 11,
    fontWeight: '700',
    color: '#1A1A2E',
    marginTop: 8,
    textAlign: 'center',
  },
  indicatorRow: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  hint: {
    fontSize: 10,
    color: '#C9A84C',
    letterSpacing: 1,
  },
});
