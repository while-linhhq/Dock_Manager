import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { portApi } from '../../port/services/portApi';
import { PATHS } from '../../../router/paths';
import type { CameraRead } from '../../../types/api.types';
import { cameraGroupsApi } from '../services/camera-groups-api';
import { useFusionEditorStore } from '../store/fusion-editor-store';
import type { CameraGroupMember, PipelineMode } from '../types/fusion.types';
import { FusionCanvas } from '../components/FusionCanvas';
import { MemberList } from '../components/MemberList';
import { BeFusedPreview } from '../components/BeFusedPreview';
import { LockBackgroundButton } from '../../seam-anchor';
import {
  moveMemberInCameraOrder,
  normalizeMemberPriorities,
  sortMembersByCameraOrder,
} from '../utils/camera-group-order';

export const FusionGroupEditorView: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = !id || id === 'new';
  const [cameras, setCameras] = useState<CameraRead[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [pipelineMode, setPipelineMode] = useState<PipelineMode>('hybrid');
  const [canvasWidth, setCanvasWidth] = useState(1920);
  const [canvasHeight, setCanvasHeight] = useState(1080);
  const [isActive, setIsActive] = useState(true);
  const [members, setMembers] = useState<CameraGroupMember[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const { selectedMemberCameraId, setSelectedMemberCameraId } = useFusionEditorStore();

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
        setPipelineMode(group.pipeline_mode ?? 'hybrid');
        setCanvasWidth(group.canvas_width);
        setCanvasHeight(group.canvas_height);
        setIsActive(group.is_active);
        setMembers(normalizeMemberPriorities(group.members));
        setSelectedMemberCameraId(group.members[0]?.camera_id ?? null);
      })
      .catch(console.error);
  }, [id, isNew, setSelectedMemberCameraId]);

  const orderedMembers = useMemo(() => sortMembersByCameraOrder(members), [members]);
  const groupIdNumber = useMemo(() => {
    if (isNew || !id) {
      return null;
    }
    const parsed = Number(id);
    return Number.isFinite(parsed) ? parsed : null;
  }, [id, isNew]);

  const moveMember = (cameraId: number, direction: -1 | 1) => {
    setMembers((current) => moveMemberInCameraOrder(current, cameraId, direction));
  };

  const save = async () => {
    setIsSaving(true);
    try {
      const payload = {
        name: name.trim() || 'Untitled Fusion Group',
        description: description.trim() || null,
        fusion_mode: 'layout' as const,
        pipeline_mode: pipelineMode,
        canvas_width: canvasWidth,
        canvas_height: canvasHeight,
        is_active: isActive,
        members: normalizeMemberPriorities(members),
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
            value={pipelineMode}
            onChange={(event) => setPipelineMode(event.target.value as PipelineMode)}
          >
            <option value="hybrid">Camera rời rạc (đa luồng)</option>
            <option value="fused">Frame ghép thủ công</option>
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
              members={orderedMembers}
              selectedCameraId={selectedMemberCameraId}
              onSelect={setSelectedMemberCameraId}
              onMembersChange={setMembers}
            />
            <CameraOrderPanel members={orderedMembers} onMove={moveMember} />
            <SeamAnchorPanel groupId={groupIdNumber} members={orderedMembers} />
            <BeFusedPreview
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

const SeamAnchorPanel: React.FC<{
  groupId: number | null;
  members: CameraGroupMember[];
}> = ({ groupId, members }) => {
  const cameraIds = members.map((member) => Number(member.camera_id));
  const groupSaved = groupId !== null;
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#121214]">
      <div className="mb-4">
        <p className="text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
          Seam Anchor — nền cảng tham chiếu
        </p>
        <p className="text-xs text-gray-500">
          Chụp frame "cảng trống không có tàu" làm background. Khi tàu neo bị chia 2 camera ở vùng giáp ranh,
          mô hình so sánh với nền này để giữ ID đang neo và tính thời gian đúng.
        </p>
      </div>
      {!groupSaved ? (
        <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">
          Lưu group trước, sau đó quay lại để chụp nền tham chiếu.
        </p>
      ) : null}
      <div className="flex flex-wrap items-start gap-3">
        <LockBackgroundButton
          groupId={groupId ?? undefined}
          forceCapture
          disabled={!groupSaved || cameraIds.length === 0}
          label="Lock all in group"
        />
        {members.map((member) => (
          <LockBackgroundButton
            key={member.camera_id}
            groupId={groupId ?? undefined}
            cameraIds={[Number(member.camera_id)]}
            forceCapture
            disabled={!groupSaved}
            size="sm"
            label={member.camera?.camera_name ?? `Camera ${member.camera_id}`}
          />
        ))}
      </div>
    </div>
  );
};

const CameraOrderPanel: React.FC<{
  members: CameraGroupMember[];
  onMove: (cameraId: number, direction: -1 | 1) => void;
}> = ({ members, onMove }) => (
  <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#121214]">
    <div className="mb-4">
      <p className="text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
        Thứ tự camera trái sang phải
      </p>
      <p className="text-xs text-gray-500">
        Thứ tự trái → phải dọc theo luồng tàu. Chỉ dùng cho Re-ID hybrid (match camera liền kề).
        Vị trí tile trên canvas vẫn chỉnh bằng X/Y.
      </p>
    </div>
    {members.length < 2 ? (
      <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">
        Thêm ít nhất 2 camera để chỉnh thứ tự trái / phải.
      </p>
    ) : null}
    <div className="grid gap-2">
      {members.map((member, index) => (
        <div
          key={member.camera_id}
          className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2 text-xs dark:bg-white/5"
        >
          <span className="font-semibold text-gray-700 dark:text-gray-200">
            {index + 1}. {member.camera?.camera_name ?? `Camera ${member.camera_id}`}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 disabled:opacity-40 dark:border-white/10 dark:text-gray-300"
              disabled={index === 0}
              onClick={() => onMove(Number(member.camera_id), -1)}
            >
              ← Trái
            </button>
            <button
              type="button"
              className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 disabled:opacity-40 dark:border-white/10 dark:text-gray-300"
              disabled={index === members.length - 1}
              onClick={() => onMove(Number(member.camera_id), 1)}
            >
              Phải →
            </button>
          </div>
        </div>
      ))}
    </div>
  </div>
);
