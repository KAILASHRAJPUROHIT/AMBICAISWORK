import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';

export type Enquiry = {
  id: string;
  productId: string;
  productName: string;
  category: string;
  message: string;
  status: 'sent' | 'replied' | 'pending';
  createdAt: string;
};

const KEY = 'aradhana.enquiries.v1';

const EnquiryContext = createContext<{
  enquiries: Enquiry[];
  add: (enquiry: Omit<Enquiry, 'id' | 'createdAt'>) => void;
  markReplied: (id: string) => void;
  remove: (id: string) => void;
  count: number;
}>({
  enquiries: [],
  add: () => {},
  markReplied: () => {},
  remove: () => {},
  count: 0,
});

export function EnquiryProvider({ children }: { children: ReactNode }) {
  const [enquiries, setEnquiries] = useState<Enquiry[]>([]);

  useEffect(() => {
    let mounted = true;
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (mounted && raw) {
          try {
            setEnquiries(JSON.parse(raw) as Enquiry[]);
          } catch {
            // corrupted storage, ignore
          }
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  const persist = useCallback((next: Enquiry[]) => {
    AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
  }, []);

  const add = useCallback(
    (enquiry: Omit<Enquiry, 'id' | 'createdAt'>) => {
      const newEnquiry: Enquiry = {
        ...enquiry,
        id: `enq_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        createdAt: new Date().toISOString(),
      };
      setEnquiries((prev) => {
        const next = [newEnquiry, ...prev];
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const markReplied = useCallback(
    (id: string) => {
      setEnquiries((prev) => {
        const next = prev.map((e) =>
          e.id === id ? { ...e, status: 'replied' as const } : e,
        );
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const remove = useCallback(
    (id: string) => {
      setEnquiries((prev) => {
        const next = prev.filter((e) => e.id !== id);
        persist(next);
        return next;
      });
    },
    [persist],
  );

  return (
    <EnquiryContext.Provider
      value={{ enquiries, add, markReplied, remove, count: enquiries.length }}>
      {children}
    </EnquiryContext.Provider>
  );
}

export function useEnquiries() {
  return useContext(EnquiryContext);
}
