import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { usePortStore } from '../store/portStore';
import type { CameraCreate, PortConfigCreate, PipelineStartRequest, PortConfigRead } from '../services/portApi';
import { getDetectionDisplayTimeIso, getDetectionShipLabel } from '../../../utils/detection-display';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import type { CameraRead } from '../../../types/api.types';
import { cameraSchema, configSchema, pipelineSchema } from '../port-schemas';
import { PortMainTabs, type PortMainTab } from '../components/PortMainTabs';
import { PortDetectionsSection } from '../components/PortDetectionsSection';
import { PortCamerasSection } from '../components/PortCamerasSection';
import { PortConfigsSection } from '../components/PortConfigsSection';
import { PortPipelineSection } from '../components/PortPipelineSection';
import { PortModals } from '../components/PortModals';

export const PortView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<PortMainTab>('detections');
  const [isCameraModalOpen, setIsCameraModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [isPipelineModalOpen, setIsPipelineModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingConfigKey, setEditingConfigKey] = useState<string | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');
  const [pipelineTabCameraId, setPipelineTabCameraId] = useState<string>('');
  const [pipelineTabEnableOcr, setPipelineTabEnableOcr] = useState(true);
  const [detQ, setDetQ] = useState('');
  const [detAccepted, setDetAccepted] = useState<'all' | 'yes' | 'no'>('all');
  const [detDateFrom, setDetDateFrom] = useState('');
  const [detDateTo, setDetDateTo] = useState('');
  const [detMinConfPct, setDetMinConfPct] = useState('');
  const [camQ, setCamQ] = useState('');
  const [camActive, setCamActive] = useState<'all' | 'on' | 'off'>('all');
  const [cfgKeyQ, setCfgKeyQ] = useState('');
  const [cfgValQ, setCfgValQ] = useState('');

  const {
    detections,
    cameras,
    configs,
    isLoading,
    fetchDetections,
    fetchCameras,
    fetchConfigs,
    verifyDetection,
    upsertCamera,
    deleteCamera,
    upsertConfig,
    deleteConfig,
    deleteDetection,
    startPipeline,
    stopPipeline,
  } = usePortStore();

  const cameraForm = useForm<CameraCreate>({
    resolver: zodResolver(cameraSchema),
    defaultValues: { is_active: true },
  });

  const configForm = useForm<PortConfigCreate>({
    resolver: zodResolver(configSchema),
  });

  const pipelineForm = useForm<PipelineStartRequest>({
    resolver: zodResolver(pipelineSchema),
    defaultValues: { source: '', enable_ocr: true },
  });

  useEffect(() => {
    if (activeTab === 'detections') fetchDetections();
    if (activeTab === 'cameras' || activeTab === 'pipeline') fetchCameras();
    if (activeTab === 'configs') fetchConfigs();
  }, [activeTab, fetchDetections, fetchCameras, fetchConfigs]);

  useEffect(() => {
    if (!pipelineTabCameraId) {
      return;
    }
    const cam = cameras.find((c) => String(c.id) === pipelineTabCameraId);
    if (!cam || !cam.is_active) {
      setPipelineTabCameraId('');
    }
  }, [cameras, pipelineTabCameraId]);

  useEffect(() => {
    if (!selectedCameraId) {
      return;
    }
    const cam = cameras.find((c) => String(c.id) === selectedCameraId);
    if (cam && !cam.is_active) {
      setSelectedCameraId('');
    }
  }, [cameras, selectedCameraId]);

  const filteredDetections = useMemo(() => {
    return detections.filter((det) => {
      const label = getDetectionShipLabel(det);
      const iso = getDetectionDisplayTimeIso(det);
      if (
        !matchesAnyField(
          detQ,
          label,
          det.track_id,
          String(det.vessel_id ?? ''),
          det.vessel?.ship_id,
        )
      ) {
        return false;
      }
      if (detAccepted === 'yes' && det.is_accepted !== true) {
        return false;
      }
      if (detAccepted === 'no' && det.is_accepted === true) {
        return false;
      }
      if (!isoInLocalDateRange(iso ?? det.created_at, detDateFrom, detDateTo)) {
        return false;
      }
      if (detMinConfPct.trim()) {
        const min = Number(detMinConfPct);
        const c = Number(det.confidence ?? 0) * 100;
        if (!Number.isFinite(min) || c < min) {
          return false;
        }
      }
      return true;
    });
  }, [detections, detQ, detAccepted, detDateFrom, detDateTo, detMinConfPct]);

  const filteredCameras = useMemo(() => {
    return cameras.filter((cam) => {
      if (!matchesAnyField(camQ, cam.camera_name, cam.name, cam.rtsp_url)) {
        return false;
      }
      if (camActive === 'on' && !cam.is_active) {
        return false;
      }
      if (camActive === 'off' && cam.is_active) {
        return false;
      }
      return true;
    });
  }, [cameras, camQ, camActive]);

  const filteredConfigs = useMemo(() => {
    return configs.filter((cfg) => {
      if (!matchesAnyField(cfgKeyQ, cfg.key)) {
        return false;
      }
      if (!matchesAnyField(cfgValQ, cfg.value, cfg.description)) {
        return false;
      }
      return true;
    });
  }, [configs, cfgKeyQ, cfgValQ]);

  const detFilterCount =
    (detQ.trim() ? 1 : 0) +
    (detAccepted !== 'all' ? 1 : 0) +
    (detDateFrom ? 1 : 0) +
    (detDateTo ? 1 : 0) +
    (detMinConfPct.trim() ? 1 : 0);

  const camFilterCount = (camQ.trim() ? 1 : 0) + (camActive !== 'all' ? 1 : 0);

  const cfgFilterCount = (cfgKeyQ.trim() ? 1 : 0) + (cfgValQ.trim() ? 1 : 0);

  const resetDetFilters = () => {
    setDetQ('');
    setDetAccepted('all');
    setDetDateFrom('');
    setDetDateTo('');
    setDetMinConfPct('');
  };

  const resetCamFilters = () => {
    setCamQ('');
    setCamActive('all');
  };

  const resetCfgFilters = () => {
    setCfgKeyQ('');
    setCfgValQ('');
  };

  const onCameraSubmit = async (data: CameraCreate) => {
    try {
      await upsertCamera(editingId, data);
      setIsCameraModalOpen(false);
      cameraForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onConfigSubmit = async (data: PortConfigCreate) => {
    try {
      await upsertConfig(editingConfigKey, data);
      setIsConfigModalOpen(false);
      configForm.reset();
      setEditingConfigKey(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onPipelineSubmit = async (data: PipelineStartRequest) => {
    try {
      const payload: PipelineStartRequest = {
        enable_ocr: data.enable_ocr,
      };
      if (selectedCameraId) {
        const picked = cameras.find((c) => String(c.id) === selectedCameraId);
        if (picked && !picked.is_active) {
          window.alert(
            'Camera này đang tắt «Kích hoạt». Bật trong tab Camera, hoặc chỉ dùng nguồn RTSP thủ công (bỏ chọn camera).',
          );
          return;
        }
        payload.camera_id = Number(selectedCameraId);
      } else if (data.source && data.source.trim()) {
        payload.source = data.source.trim();
      }
      await startPipeline(payload);
      setIsPipelineModalOpen(false);
      setSelectedCameraId('');
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditCamera = (cam: CameraRead) => {
    setEditingId(String(cam.id));
    cameraForm.reset({
      name: cam.camera_name || cam.name || '',
      rtsp_url: cam.rtsp_url,
      is_active: cam.is_active,
    });
    setIsCameraModalOpen(true);
  };

  const handleDeleteCamera = async (cam: CameraRead) => {
    const label = cam.camera_name || cam.name || `Camera ${cam.id}`;
    if (!window.confirm(`Xóa vĩnh viễn camera «${label}»? Hành động không hoàn tác.`)) {
      return;
    }
    try {
      if (editingId != null && String(editingId) === String(cam.id)) {
        setIsCameraModalOpen(false);
        setEditingId(null);
        cameraForm.reset({ is_active: true });
      }
      if (String(selectedCameraId) === String(cam.id)) {
        setSelectedCameraId('');
      }
      if (String(pipelineTabCameraId) === String(cam.id)) {
        setPipelineTabCameraId('');
      }
      await deleteCamera(cam.id);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditConfig = (cfg: PortConfigRead) => {
    setEditingConfigKey(cfg.key);
    configForm.reset({
      key: cfg.key,
      value: cfg.value,
      description: cfg.description || '',
    });
    setIsConfigModalOpen(true);
  };

  const handleDeleteConfig = async (key: string) => {
    if (!window.confirm(`Xác nhận xóa config "${key}"?`)) {
      return;
    }
    await deleteConfig(key);
  };

  const handleDeleteDetection = async (id: string) => {
    if (!window.confirm('Xác nhận xóa bản ghi nhận diện này?')) {
      return;
    }
    await deleteDetection(id);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <PortMainTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === 'detections' && (
        <PortDetectionsSection
          detQ={detQ}
          setDetQ={setDetQ}
          detAccepted={detAccepted}
          setDetAccepted={setDetAccepted}
          detDateFrom={detDateFrom}
          setDetDateFrom={setDetDateFrom}
          detDateTo={detDateTo}
          setDetDateTo={setDetDateTo}
          detMinConfPct={detMinConfPct}
          setDetMinConfPct={setDetMinConfPct}
          resetDetFilters={resetDetFilters}
          detFilterCount={detFilterCount}
          onRefresh={() => fetchDetections()}
          isLoading={isLoading}
          detections={detections}
          filteredDetections={filteredDetections}
          onVerify={(id, data) => verifyDetection(id, data)}
          onDeleteDetection={handleDeleteDetection}
        />
      )}

      {activeTab === 'cameras' && (
        <PortCamerasSection
          camQ={camQ}
          setCamQ={setCamQ}
          camActive={camActive}
          setCamActive={setCamActive}
          resetCamFilters={resetCamFilters}
          camFilterCount={camFilterCount}
          onOpenAddCamera={() => {
            setEditingId(null);
            cameraForm.reset({ is_active: true });
            setIsCameraModalOpen(true);
          }}
          filteredCameras={filteredCameras}
          cameras={cameras}
          isLoading={isLoading}
          onEditCamera={handleEditCamera}
          onDeleteCamera={handleDeleteCamera}
        />
      )}

      {activeTab === 'configs' && (
        <PortConfigsSection
          cfgKeyQ={cfgKeyQ}
          setCfgKeyQ={setCfgKeyQ}
          cfgValQ={cfgValQ}
          setCfgValQ={setCfgValQ}
          resetCfgFilters={resetCfgFilters}
          cfgFilterCount={cfgFilterCount}
          onOpenAddConfig={() => {
            setEditingConfigKey(null);
            configForm.reset({ key: '', value: '', description: '' });
            setIsConfigModalOpen(true);
          }}
          filteredConfigs={filteredConfigs}
          configs={configs}
          onEditConfig={handleEditConfig}
          onDeleteConfig={handleDeleteConfig}
        />
      )}

      {activeTab === 'pipeline' && (
        <PortPipelineSection
          cameras={cameras}
          isLoading={isLoading}
          startPipeline={startPipeline}
          stopPipeline={stopPipeline}
          pipelineTabCameraId={pipelineTabCameraId}
          setPipelineTabCameraId={setPipelineTabCameraId}
          pipelineTabEnableOcr={pipelineTabEnableOcr}
          setPipelineTabEnableOcr={setPipelineTabEnableOcr}
          setSelectedCameraId={setSelectedCameraId}
          pipelineForm={pipelineForm}
          onOpenCustomSourceModal={() => setIsPipelineModalOpen(true)}
        />
      )}

      <PortModals
        isCameraModalOpen={isCameraModalOpen}
        onCloseCamera={() => setIsCameraModalOpen(false)}
        cameraForm={cameraForm}
        onCameraSubmit={onCameraSubmit}
        editingCameraId={editingId}
        isLoading={isLoading}
        isConfigModalOpen={isConfigModalOpen}
        onCloseConfig={() => setIsConfigModalOpen(false)}
        configForm={configForm}
        onConfigSubmit={onConfigSubmit}
        editingConfigKey={editingConfigKey}
        isPipelineModalOpen={isPipelineModalOpen}
        onClosePipeline={() => setIsPipelineModalOpen(false)}
        pipelineForm={pipelineForm}
        onPipelineSubmit={onPipelineSubmit}
        selectedCameraId={selectedCameraId}
        setSelectedCameraId={setSelectedCameraId}
        cameras={cameras}
      />
    </div>
  );
};
