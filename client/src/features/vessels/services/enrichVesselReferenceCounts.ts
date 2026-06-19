import type { VesselRead } from '../../../types/api.types';
import { vesselsApi } from './vesselsApi';

const ENRICH_CONCURRENCY = 8;

async function enrichCountsPerVessel(vessels: VesselRead[]): Promise<VesselRead[]> {
  const enriched = [...vessels];
  for (let index = 0; index < enriched.length; index += ENRICH_CONCURRENCY) {
    const chunk = enriched.slice(index, index + ENRICH_CONCURRENCY);
    await Promise.all(
      chunk.map(async (vessel, chunkIndex) => {
        const targetIndex = index + chunkIndex;
        try {
          const response = await vesselsApi.getVesselReferenceImages(String(vessel.id));
          enriched[targetIndex] = {
            ...vessel,
            visual_reference_count: response.count ?? response.items?.length ?? 0,
          };
        } catch {
          enriched[targetIndex] = { ...vessel, visual_reference_count: 0 };
        }
      }),
    );
  }
  return enriched;
}

export async function enrichVesselReferenceCounts(vessels: VesselRead[]): Promise<VesselRead[]> {
  if (vessels.length === 0) {
    return vessels;
  }
  if (typeof vessels[0].visual_reference_count === 'number') {
    return vessels;
  }

  try {
    const { counts } = await vesselsApi.getVisualReferenceCounts();
    return vessels.map((vessel) => ({
      ...vessel,
      visual_reference_count: counts[vessel.ship_id] ?? 0,
    }));
  } catch {
    return enrichCountsPerVessel(vessels);
  }
}
