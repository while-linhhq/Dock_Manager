import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { portApi } from '../../port/services/portApi';
import { PATHS } from '../../../router/paths';
import type { CameraRead } from '../../../types/api.types';
import { cameraGroupsApi } from '../services/camera-groups-api';
import { useFusionEditorStore } from '../store/fusion-editor-store';
import type { CameraGroupMember, FusionMode } from '../types/fusion.types';
import { FusionCanvas } from '../components/FusionCanvas';
import { MemberList } from '../components/MemberList';
import { BeFusedPreview } from '../components/BeFusedPreview';
import { CalibrationPanel } from '../components/CalibrationPanel';

export const FusionGroupEditorView: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = !id || id === 'new';
  const [cameras, setCameras] = useState<CameraRead[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [fusionMode, setFusionMode] = useState<FusionMode>('layout');
  const [canvasWidth, setCanvasWidth] = useState(1920);
  const [canvasHeight, setCanvasHeight] = useState(1080);
  const [isActive, setIsActive] = useState(true);
  const [members, setMembers] = useState<CameraGroupMember[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const { selectedMemberCameraId, setSelectedMemberCameraId, mode, setMode } = useFusionEditorStore();

  useEffect(() => {
    portApi.getCameras(false).then(setCameras).catch(console.error);
  }, []);

  useEffect(() => {
    if (isNew || !id) {
      return;
    }
    cameraGroupsApi
      .get(id)
      .then((group) => {
        setName(group.name);
        setDescription(group.description ?? '');
        setFusionMode(group.fusion_mode);
        setCanvasWidth(group.canvas_width);
        setCanvasHeight(group.canvas_height);
        setIsActive(group.is_active);
        setMembers(group.members);
        setSelectedMemberCameraId(group.members[0]?.camera_id ?? null);
      })
      .catch(console.error);
  }, [id, isNew, setSelectedMemberCameraId]);

  const selectedMember = useMemo(
    () => members.find((member) => member.camera_id === selectedMemberCameraId),
    [members, selectedMemberCameraId],
  );

  const save = async () => {
    setIsSaving(true);
    try {
      const payload = {
        name: name.trim() || 'Untitled Fusion Group',
        description: description.trim() || null,
        fusion_mode: fusionMode,
        canvas_width: canvasWidth,
        canvas_height: canvasHeight,
        is_active: isActive,
        members,
      };
      const group = isNew
        ? await cameraGroupsApi.create(payload)
        : await cameraGroupsApi.update(id!, payload);
      navigate(`${PATHS.CAMERA_FUSION}/${group.id}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <Link
              to={PATHS.CAMERA_FUSION}
              className="mb-2 inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-blue-500"
            >
              <ArrowLeft className="h-4 w-4" /> Back to groups
            </Link>
            <h1 className="text-2xl font-black tracking-tight text-gray-900 dark:text-white">
              Fusion Group Editor
            </h1>
            <p className="text-sm text-gray-500">
              FE chỉ pick cấu hình. Fused preview thật được BE render và dùng lại cho YOLO.
            </p>
          </div>
          <Button onClick={save} disabled={isSaving} className="flex items-center gap-2">
            <Save className="h-4 w-4" />
            Save
          </Button>
        </div>

        <div className="grid gap-4 rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#121214] md:grid-cols-5">
          <input
            className="rounded-xl border border-gray-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white md:col-span-2"
            placeholder="Group name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <select
            className="rounded-xl border border-gray-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white"
            value={fusionMode}
            onChange={(event) => setFusionMode(event.target.value as FusionMode)}
          >
            <option value="layout">Layout</option>
            <option value="homography">Homography</option>
            <option value="panorama">Panorama</option>
          </select>
          <input
            type="number"
            className="rounded-xl border border-gray-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white"
            value={canvasWidth}
            onChange={(event) => setCanvasWidth(Number(event.target.value))}
          />
          <input
            type="number"
            className="rounded-xl border border-gray-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white"
            value={canvasHeight}
            onChange={(event) => setCanvasHeight(Number(event.target.value))}
          />
          <textarea
            className="rounded-xl border border-gray-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white md:col-span-4"
            placeholder="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <label className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-gray-500">
            <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
            Active
          </label>
        </div>

        <div className="flex gap-2">
          <Button variant={mode === 'layout' ? 'primary' : 'outline'} onClick={() => setMode('layout')}>
            Layout
          </Button>
          <Button variant={mode === 'calibrate' ? 'primary' : 'outline'} onClick={() => setMode('calibrate')}>
            Calibration
          </Button>
        </div>

        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <MemberList
            cameras={cameras}
            members={members}
            selectedCameraId={selectedMemberCameraId}
            onSelect={setSelectedMemberCameraId}
            onMembersChange={setMembers}
          />
          <div className="space-y-6">
            <FusionCanvas
              canvasWidth={canvasWidth}
              canvasHeight={canvasHeight}
              members={members}
              selectedCameraId={selectedMemberCameraId}
              onSelect={setSelectedMemberCameraId}
              onMembersChange={setMembers}
            />
            {mode === 'calibrate' ? (
              <CalibrationPanel
                groupId={isNew ? null : Number(id)}
                member={selectedMember}
                members={members}
                onMembersChange={setMembers}
                onCanvasChange={(width, height) => {
                  setCanvasWidth(width);
                  setCanvasHeight(height);
                  setFusionMode('panorama');
                }}
              />
            ) : null}
            <BeFusedPreview
              fusionMode={fusionMode}
              canvasWidth={canvasWidth}
              canvasHeight={canvasHeight}
              members={members}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
