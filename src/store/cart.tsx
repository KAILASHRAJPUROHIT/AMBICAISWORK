import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';

export type CartItem = {
  productId: string;
  addedAt: string;
};

const KEY = 'aradhana.cart.v1';

const CartContext = createContext<{
  items: CartItem[];
  add: (productId: string) => void;
  remove: (productId: string) => void;
  has: (productId: string) => boolean;
  count: number;
  clear: () => void;
}>({
  items: [],
  add: () => {},
  remove: () => {},
  has: () => false,
  count: 0,
  clear: () => {},
});

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);

  useEffect(() => {
    let mounted = true;
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (mounted && raw) setItems(JSON.parse(raw) as CartItem[]);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  const persist = useCallback((next: CartItem[]) => {
    AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
  }, []);

  const add = useCallback(
    (productId: string) => {
      setItems((prev) => {
        if (prev.some((i) => i.productId === productId)) return prev;
        const next = [...prev, { productId, addedAt: new Date().toISOString() }];
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const remove = useCallback(
    (productId: string) => {
      setItems((prev) => {
        const next = prev.filter((i) => i.productId !== productId);
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const has = useCallback((productId: string) => items.some((i) => i.productId === productId), [items]);

  const clear = useCallback(() => {
    setItems([]);
    persist([]);
  }, [persist]);

  return (
    <CartContext.Provider value={{ items, add, remove, has, count: items.length, clear }}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  return useContext(CartContext);
}
