/**
 * Web rider location broadcaster — posts GPS every configured interval while online.
 */
import { useEffect, useRef, useState } from 'react';

import { api, ApiError } from '@/api/client';
import { config } from '@/config';

export type LocationStatus =
  | 'idle'
  | 'requesting'
  | 'denied'
  | 'tracking'
  | 'error';

export function useRiderLocationBroadcast(active: boolean) {
  const [status, setStatus] = useState<LocationStatus>('idle');
  const [lastError, setLastError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);

  useEffect(() => {
    const stop = () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };

    if (!active) {
      stop();
      setStatus('idle');
      return stop;
    }

    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setStatus('error');
      setLastError('Geolocation is not available in this browser');
      return stop;
    }

    let cancelled = false;
    setStatus('requesting');

    const send = (coords: GeolocationCoordinates) => {
      if (!Number.isFinite(coords.latitude) || !Number.isFinite(coords.longitude)) return;
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      void api.postLocation({
        lat: coords.latitude,
        lng: coords.longitude,
        accuracy: coords.accuracy ?? undefined,
        heading: coords.heading ?? undefined,
        speed: coords.speed ?? undefined,
        client_timestamp: new Date().toISOString(),
      }).then(() => {
        if (!cancelled) {
          setStatus('tracking');
          setLastError(null);
        }
      }).catch((err) => {
        if (!cancelled && err instanceof ApiError) setLastError(err.message);
      }).finally(() => {
        inFlightRef.current = false;
      });
    };

    const tick = () => {
      navigator.geolocation.getCurrentPosition(
        (pos) => send(pos.coords),
        (err) => {
          if (cancelled) return;
          if (err.code === err.PERMISSION_DENIED) setStatus('denied');
          else setStatus('error');
          setLastError(err.message || 'Could not read location');
        },
        // Desktop browsers have no GPS; forcing fresh high-accuracy fixes
        // (maximumAge:0) makes getCurrentPosition time out. Allow a recent
        // cached fix and network-based accuracy so web tracking is reliable.
        { enableHighAccuracy: false, timeout: 27000, maximumAge: 15000 },
      );
    };

    tick();
    timerRef.current = setInterval(tick, config.locationIntervalMs);
    setStatus('tracking');

    return () => {
      cancelled = true;
      stop();
    };
  }, [active]);

  return { status, lastError };
}
