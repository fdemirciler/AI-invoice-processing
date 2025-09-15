import { useEffect, useRef, useState } from 'react';
import { resetSessionId } from '@/lib/session';

export interface UseSessionReturn {
  sessionId: string;
  resetSession: () => void;
}

/**
 * Manage a per-tab session id. Behavior matches existing app: create a brand new
 * session on each page load, and allow manual resets.
 */
export function useSession(): UseSessionReturn {
  const [sessionId, setSessionId] = useState<string>('');
  const mountedRef = useRef(false);

  useEffect(() => {
    // On mount, always create a brand new session id (matches previous behavior)
    const sid = resetSessionId();
    setSessionId(sid);
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const resetSession = () => {
    const sid = resetSessionId();
    setSessionId(sid);
  };

  return { sessionId, resetSession };
}
