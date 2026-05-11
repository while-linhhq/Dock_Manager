import { create } from 'zustand';

type FusionEditorState = {
  selectedMemberCameraId: number | null;
  setSelectedMemberCameraId: (cameraId: number | null) => void;
};

export const useFusionEditorStore = create<FusionEditorState>((set) => ({
  selectedMemberCameraId: null,
  setSelectedMemberCameraId: (selectedMemberCameraId) => set({ selectedMemberCameraId }),
}));
