import { useCallback, useEffect, useRef, useState } from 'react';
import type { Limits } from '@/types/api';
import { getConfig } from '@/lib/api';

export interface UseConfigReturn {
  limits: Limits | null;
  isLoading: boolean;
  error?: string;
  reload: () => Promise<void>;
}

export function useConfig(initiallyLoad: boolean = false): UseConfigReturn {
  const [limits, setLimits] = useState<Limits | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const mounted = useRef(true);

  useEffect(() => () => { mounted.current = false; }, []);

  const reload = useCallback(async () => {
    setIsLoading(true);
    setError(undefined);
    try {
      const cfg = await getConfig();
      if (!mounted.current) return;
      setLimits(cfg);
    } catch (e: any) {
      if (!mounted.current) return;
      setError(String(e?.message || e));
    } finally {
      if (!mounted.current) return;
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initiallyLoad) void reload();
  }, [initiallyLoad, reload]);

  return { limits, isLoading, error, reload };
}
