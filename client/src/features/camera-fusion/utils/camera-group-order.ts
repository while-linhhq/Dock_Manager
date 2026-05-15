import type { CameraGroupMember } from '../types/fusion.types';

/** Left-to-right dock order: lower priority = further left. */
export function sortMembersByCameraOrder(members: CameraGroupMember[]): CameraGroupMember[] {
  return [...members].sort(
    (left, right) =>
      left.priority - right.priority || left.camera_id - right.camera_id,
  );
}

export function normalizeMemberPriorities(
  members: CameraGroupMember[],
): CameraGroupMember[] {
  return assignPrioritiesByOrder(sortMembersByCameraOrder(members));
}

function assignPrioritiesByOrder(ordered: CameraGroupMember[]): CameraGroupMember[] {
  return ordered.map((member, index) => ({
    ...member,
    priority: index,
  }));
}

export function moveMemberInCameraOrder(
  members: CameraGroupMember[],
  cameraId: number,
  direction: -1 | 1,
): CameraGroupMember[] {
  const ordered = sortMembersByCameraOrder(members);
  const targetId = Number(cameraId);
  const currentIndex = ordered.findIndex(
    (member) => Number(member.camera_id) === targetId,
  );
  const nextIndex = currentIndex + direction;
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= ordered.length) {
    return members;
  }
  const nextOrdered = [...ordered];
  [nextOrdered[currentIndex], nextOrdered[nextIndex]] = [
    nextOrdered[nextIndex],
    nextOrdered[currentIndex],
  ];
  // Gán priority theo vị trí mới — không sort lại theo priority cũ (sẽ undo swap).
  return assignPrioritiesByOrder(nextOrdered);
}
