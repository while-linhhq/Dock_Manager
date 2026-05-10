import { useEffect, useState } from 'react';
import type { VesselRead, VesselTypeRead } from '../types/api.types';
import { vesselsApi } from '../features/vessels/services/vesselsApi';

export function useFilterOptions() {
  const [vessels, setVessels] = useState<VesselRead[]>([]);
  const [vesselTypes, setVesselTypes] = useState<VesselTypeRead[]>([]);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      vesselsApi.getVessels(0, 1000, false),
      vesselsApi.getVesselTypes(),
    ])
      .then(([nextVessels, nextVesselTypes]) => {
        if (cancelled) {
          return;
        }
        setVessels(nextVessels);
        setVesselTypes(nextVesselTypes);
      })
      .catch(console.error);

    return () => {
      cancelled = true;
    };
  }, []);

  return { vessels, vesselTypes };
}
