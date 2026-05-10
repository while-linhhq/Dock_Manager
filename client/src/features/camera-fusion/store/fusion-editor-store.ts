import { create } from 'zustand';
import type { CalibrationPointPair } from '../types/fusion.types';

type FusionEditorState = {
  selectedMemberCameraId: number | null;
  mode: 'layout' | 'calibrate';
  calibrationPoints: CalibrationPointPair[];
  setSelectedMemberCameraId: (cameraId: number | null) => void;
  setMode: (mode: 'layout' | 'calibrate') => void;
  setCalibrationPoints: (points: CalibrationPointPair[]) => void;
};

export const useFusionEditorStore = create<FusionEditorState>((set) => ({
  selectedMemberCameraId: null,
  mode: 'layout',
  calibrationPoints: [],
  setSelectedMemberCameraId: (selectedMemberCameraId) => set({ selectedMemberCameraId }),
  setMode: (mode) => set({ mode }),
  setCalibrationPoints: (calibrationPoints) => set({ calibrationPoints }),
}));
