import React, { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import type { DetectionMediaRead } from '../../types/api.types';
import { fetchDetectionCompareMedia } from '../../services/detectionCompareService';
import { resolveDetectionMediaUrl } from '../../utils/detection-media';

export type DetectionCompareModalProps = {
  open: boolean;
  onClose: () => void;
  shipLabel: string;
  detectionId?: string | number | null;
  contextLabel?: string;
};

export const DetectionCompareModal: React.FC<DetectionCompareModalProps> = ({
  open,
  onClose,
  shipLabel,
  detectionId,
  contextLabel,
}) => {
  const [compareMedia, setCompareMedia] = useState<DetectionMediaRead[]>([]);
  const [compareLoading, setCompareLoading] = useState(false);
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setCompareMedia([]);
      setPreviewImageUrl(null);
      return;
    }
    if (detectionId == null || detectionId === '') {
      setCompareMedia([]);
      setCompareLoading(false);
      return;
    }

    let cancelled = false;
    setCompareLoading(true);
    void fetchDetectionCompareMedia(detectionId)
      .then((media) => {
        if (!cancelled) {
          setCompareMedia(media);
        }
      })
      .catch((error) => {
        console.error(error);
        if (!cancelled) {
          setCompareMedia([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCompareLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open, detectionId]);

  if (!open) {
    return null;
  }

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 sm:p-6 lg:pl-[calc(256px+1.5rem)]">
        <button
          type="button"
          className="absolute inset-0"
          aria-label="Đóng đối chiếu"
          onClick={onClose}
        />
        <div className="relative z-10 h-[90vh] w-full max-w-7xl overflow-hidden rounded-2xl border border-white/15 bg-[#0e1014]">
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wider text-white">
                Đối chiếu nhận diện
              </p>
              <p className="text-xs text-gray-300">Tàu: {shipLabel}</p>
              {contextLabel ? (
                <p className="text-xs text-gray-400">{contextLabel}</p>
              ) : null}
            </div>
            <button
              type="button"
              className="rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
              onClick={onClose}
              aria-label="Đóng"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="h-[calc(90vh-61px)] overflow-y-auto p-4">
            {!detectionId ? (
              <div className="flex h-full items-center justify-center text-sm text-gray-400">
                Hóa đơn không có nhận diện liên kết để đối chiếu
              </div>
            ) : compareLoading ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-blue-400" />
              </div>
            ) : compareMedia.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm uppercase tracking-wider text-gray-400">
                Không có ảnh/video đối chiếu cho detection này
              </div>
            ) : (
              <div className="space-y-6">
                <div className="space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-gray-300">
                    Ảnh xác minh
                  </h4>
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    {compareMedia
                      .filter((m) => (m.media_type || '').toLowerCase() !== 'video')
                      .map((m) => {
                        const src = resolveDetectionMediaUrl(m.file_path);
                        if (!src) {
                          return null;
                        }
                        return (
                          <button
                            key={`img-${m.id}-${m.file_path}`}
                            type="button"
                            onClick={() => setPreviewImageUrl(src)}
                            className="overflow-hidden rounded-xl border border-white/10 bg-black/40"
                          >
                            <img src={src} alt="Ảnh đối chiếu" className="h-72 w-full object-cover" />
                          </button>
                        );
                      })}
                  </div>
                </div>
                <div className="space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-gray-300">
                    Video xác minh
                  </h4>
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    {compareMedia
                      .filter((m) => (m.media_type || '').toLowerCase() === 'video')
                      .map((m) => {
                        const src = resolveDetectionMediaUrl(m.file_path);
                        if (!src) {
                          return null;
                        }
                        return (
                          <div
                            key={`video-${m.id}-${m.file_path}`}
                            className="overflow-hidden rounded-xl border border-white/10 bg-black/40 p-2"
                          >
                            <video controls preload="metadata" className="h-72 w-full rounded-lg object-contain">
                              <source src={src} type="video/mp4" />
                            </video>
                          </div>
                        );
                      })}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {previewImageUrl ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4 lg:pl-[calc(256px+1rem)]">
          <button
            type="button"
            className="absolute inset-0"
            aria-label="Đóng xem ảnh"
            onClick={() => setPreviewImageUrl(null)}
          />
          <div className="relative z-10 w-full max-w-5xl rounded-2xl border border-white/15 bg-black p-3">
            <button
              type="button"
              className="absolute right-3 top-3 rounded-full bg-black/60 p-2 text-white hover:bg-black/80"
              onClick={() => setPreviewImageUrl(null)}
              aria-label="Đóng"
            >
              <X className="h-4 w-4" />
            </button>
            <img
              src={previewImageUrl}
              alt="Ảnh xác minh nhận diện tàu"
              className="max-h-[78vh] w-full rounded-xl object-contain"
            />
          </div>
        </div>
      ) : null}
    </>
  );
};
