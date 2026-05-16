import type { CameraGroupMember } from '../../camera-fusion';
import type { SeamAnchorBbox } from '../types/seam-anchor.types';

export type FusedRectPercent = {
  leftPct: number;
  topPct: number;
  widthPct: number;
  heightPct: number;
};

export function mapCameraBboxToFusedPercent({
  bbox,
  member,
  canvasWidth,
  canvasHeight,
  sourceWidth,
  sourceHeight,
}: {
  bbox: SeamAnchorBbox;
  member: CameraGroupMember;
  canvasWidth: number;
  canvasHeight: number;
  sourceWidth: number;
  sourceHeight: number;
}): FusedRectPercent | null {
  if (canvasWidth <= 0 || canvasHeight <= 0 || sourceWidth <= 0 || sourceHeight <= 0) {
    return null;
  }

  const tileW = member.layout_w ?? sourceWidth;
  const tileH = member.layout_h ?? sourceHeight;
  const scaleX = tileW / sourceWidth;
  const scaleY = tileH / sourceHeight;
  const [x, y, w, h] = bbox;

  const fusedX = member.layout_x + x * scaleX;
  const fusedY = member.layout_y + y * scaleY;
  const fusedW = w * scaleX;
  const fusedH = h * scaleY;

  return {
    leftPct: (fusedX / canvasWidth) * 100,
    topPct: (fusedY / canvasHeight) * 100,
    widthPct: (fusedW / canvasWidth) * 100,
    heightPct: (fusedH / canvasHeight) * 100,
  };
}
