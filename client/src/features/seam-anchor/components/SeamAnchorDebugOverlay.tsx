import React, { useEffect, useMemo, useState } from 'react';
import { cameraGroupsApi, type CameraGroup } from '../../camera-fusion';
import { seamAnchorApi } from '../services/seam-anchor-api';
import type { SeamAnchorEntry, SeamAnchorStateResponse } from '../types/seam-anchor.types';
import { mapCameraBboxToFusedPercent } from '../utils/fusion-roi-map';

const POLL_MS = 2000;

type SeamAnchorDebugOverlayProps = {
  activeGroupId: number | null;
  enabled: boolean;
};

type OverlayRect = {
  key: string;
  leftPct: number;
  topPct: number;
  widthPct: number;
  heightPct: number;
  occupied: boolean;
};

function buildRects(
  group: CameraGroup,
  state: SeamAnchorStateResponse,
): OverlayRect[] {
  const threshold = state.debug?.bg_subtract_threshold ?? 0.18;
  const frameShapes = state.debug?.frame_shapes ?? {};
  const membersByCamera = new Map(
    group.members.filter((m) => m.enabled).map((m) => [m.camera_id, m]),
  );
  const rects: OverlayRect[] = [];

  const addAnchorRoi = (
    anchor: SeamAnchorEntry,
    cameraId: number,
    bbox: [number, number, number, number] | null | undefined,
    score: number,
    suffix: string,
  ) => {
    if (!bbox) return;
    const member = membersByCamera.get(cameraId);
    if (!member) return;
    const shape = frameShapes[String(cameraId)];
    const sourceH = shape?.[0] ?? member.layout_h ?? group.canvas_height;
    const sourceW = shape?.[1] ?? member.layout_w ?? group.canvas_width;
    const mapped = mapCameraBboxToFusedPercent({
      bbox,
      member,
      canvasWidth: group.canvas_width,
      canvasHeight: group.canvas_height,
      sourceWidth: sourceW,
      sourceHeight: sourceH,
    });
    if (!mapped) return;
    rects.push({
      key: `${anchor.global_id}-${suffix}`,
      ...mapped,
      occupied: score > threshold,
    });
  };

  for (const anchor of state.anchors) {
    addAnchorRoi(anchor, anchor.cam_a_id, anchor.bbox_a, anchor.last_score_a, 'A');
    if (anchor.cam_b_id != null) {
      addAnchorRoi(anchor, anchor.cam_b_id, anchor.bbox_b, anchor.last_score_b, 'B');
    }
  }

  return rects;
}

export const SeamAnchorDebugOverlay: React.FC<SeamAnchorDebugOverlayProps> = ({
  activeGroupId,
  enabled,
}) => {
  const [group, setGroup] = useState<CameraGroup | null>(null);
  const [anchorState, setAnchorState] = useState<SeamAnchorStateResponse | null>(null);

  useEffect(() => {
    if (!enabled || !activeGroupId) {
      return;
    }
    let cancelled = false;
    cameraGroupsApi
      .get(activeGroupId)
      .then((res) => {
        if (!cancelled) setGroup(res);
      })
      .catch(() => {
        if (!cancelled) setGroup(null);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, activeGroupId]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let cancelled = false;
    const fetchState = () => {
      seamAnchorApi
        .getState()
        .then((res) => {
          if (!cancelled) setAnchorState(res);
        })
        .catch(() => {
          if (!cancelled) setAnchorState(null);
        });
    };
    fetchState();
    const timer = window.setInterval(fetchState, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled]);

  const rects = useMemo(() => {
    if (!group || !anchorState?.enabled || anchorState.anchors.length === 0) {
      return [];
    }
    return buildRects(group, anchorState);
  }, [group, anchorState]);

  if (!enabled || rects.length === 0) {
    return null;
  }

  const threshold = anchorState?.debug?.bg_subtract_threshold ?? 0.18;

  return (
    <div className="pointer-events-none absolute inset-0 z-[3]">
      {rects.map((rect) => (
        <div
          key={rect.key}
          title={rect.key}
          className="absolute border-2"
          style={{
            left: `${rect.leftPct}%`,
            top: `${rect.topPct}%`,
            width: `${rect.widthPct}%`,
            height: `${rect.heightPct}%`,
            borderColor: rect.occupied ? 'rgb(52 211 153)' : 'rgb(248 113 113)',
            backgroundColor: rect.occupied
              ? 'rgba(52, 211, 153, 0.12)'
              : 'rgba(248, 113, 113, 0.08)',
          }}
        />
      ))}
      <div className="absolute left-2 top-2 rounded bg-black/70 px-2 py-1 font-mono text-[9px] uppercase tracking-widest text-emerald-300">
        Seam debug · thr {threshold.toFixed(2)} · {rects.length} ROI
      </div>
    </div>
  );
};
