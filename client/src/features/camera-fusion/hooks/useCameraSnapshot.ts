import { useEffect, useState } from 'react';
import { cameraGroupsApi } from '../services/camera-groups-api';

export function useCameraSnapshot(cameraId?: number | string | null) {
  const [url, setUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!cameraId) {
      const timer = window.setTimeout(() => {
        setUrl((previous) => {
          if (previous) {
            URL.revokeObjectURL(previous);
          }
          return null;
        });
      }, 0);
      return () => window.clearTimeout(timer);
    }
    let revokedUrl: string | null = null;
    let cancelled = false;
    const loadingTimer = window.setTimeout(() => setIsLoading(true), 0);
    cameraGroupsApi
      .snapshot(cameraId)
      .then((blob) => {
        if (cancelled) {
          return;
        }
        revokedUrl = URL.createObjectURL(blob);
        setUrl(revokedUrl);
      })
      .catch(() => {
        if (!cancelled) {
          setUrl(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
      window.clearTimeout(loadingTimer);
      if (revokedUrl) {
        URL.revokeObjectURL(revokedUrl);
      }
    };
  }, [cameraId]);

  return { url, isLoading };
}
