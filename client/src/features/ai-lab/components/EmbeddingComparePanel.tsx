import React, { useState } from 'react';
import { Loader2, ScanSearch } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { FileDropzone } from './FileDropzone';
import { resolveApiAssetUrl } from '../../../utils/resolve-api-asset-url';
import { aiLabApi } from '../services/aiLabApi';
import type { LabVisualSearchResponse } from '../types/ai-lab.types';

const ACCEPT = 'image/jpeg,image/png,image/webp';
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp'];

export const EmbeddingComparePanel: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LabVisualSearchResponse | null>(null);

  const onPickFile = (picked: File | null) => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setFile(picked);
    setResult(null);
    setError(null);
    setPreviewUrl(picked ? URL.createObjectURL(picked) : null);
  };

  const runSearch = async () => {
    if (!file) {
      return;
    }
    setIsRunning(true);
    setError(null);
    try {
      const response = await aiLabApi.visualSearch(file);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tìm kiếm embedding thất bại');
      setResult(null);
    } finally {
      setIsRunning(false);
    }
  };

  const match = result?.match ?? null;
  const matchPreview = match?.preview_url ? resolveApiAssetUrl(match.preview_url) : null;
  const rankedShips = result?.ranked_ships ?? [];

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-5 space-y-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
            So sánh embedding (Qdrant)
          </h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Kéo thả ảnh crop tàu — trích DINOv2 embedding, gom top-K theo mã tàu và kiểm tra consensus.
          </p>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <FileDropzone
            accept={ACCEPT}
            allowedExtensions={ALLOWED_EXTENSIONS}
            file={file}
            onFileChange={onPickFile}
            emptyTitle="Kéo thả ảnh query vào đây"
            emptyHint="hoặc bấm để chọn · jpg, png, webp"
            accent="violet"
          />

          <Button
            type="button"
            onClick={() => void runSearch()}
            disabled={!file || isRunning}
            className="inline-flex items-center gap-2"
          >
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            Tìm & gom theo tàu
          </Button>
        </div>

        {error ? <p className="text-sm text-red-500">{error}</p> : null}
      </div>

      {(previewUrl || result) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-gray-200 dark:border-white/10 overflow-hidden bg-black">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt="Query upload"
                className="w-full max-h-[min(60vh,640px)] object-contain bg-black"
              />
            ) : null}
            <div className="border-t border-white/10 bg-black/80 px-3 py-2 text-[10px] font-mono uppercase tracking-widest text-gray-400">
              Ảnh query
            </div>
          </div>

          <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-5 space-y-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
              Kết quả gom theo mã tàu
            </p>

            {!result ? (
              <p className="text-sm text-gray-500">Chưa có kết quả.</p>
            ) : rankedShips.length === 0 ? (
              <p className="text-sm text-amber-600 dark:text-amber-400">
                Không tìm thấy điểm nào trong collection.
              </p>
            ) : (
              <>
                <div
                  className={`rounded-xl px-4 py-5 text-center border ${
                    result.accepted
                      ? 'bg-emerald-500/10 border-emerald-500/20'
                      : 'bg-violet-500/10 border-violet-500/20'
                  }`}
                >
                  <p className="text-[10px] font-bold uppercase tracking-widest text-violet-400">
                    {result.accepted ? 'Chấp nhận' : 'Chưa đạt ngưỡng'}
                  </p>
                  {match ? (
                    <>
                      <p className="mt-2 text-4xl font-extrabold text-violet-600 dark:text-violet-300">
                        {match.similarity_percent.toFixed(1)}%
                      </p>
                      <p className="mt-1 text-sm font-mono font-semibold text-gray-900 dark:text-white">
                        {match.ship_id || '—'}
                      </p>
                      <p className="mt-1 text-xs text-gray-500">
                        margin {result.margin.toFixed(3)} · source {result.source}
                      </p>
                    </>
                  ) : (
                    <p className="mt-2 text-sm text-gray-500">Không có match hợp lệ</p>
                  )}
                </div>

                {matchPreview ? (
                  <div className="rounded-xl overflow-hidden border border-gray-200 dark:border-white/10">
                    <img
                      src={matchPreview}
                      alt="Enrolled reference"
                      className="w-full max-h-48 object-contain bg-black"
                    />
                  </div>
                ) : null}

                <div className="space-y-2">
                  {rankedShips.map((ship) => {
                    const preview = ship.preview_url ? resolveApiAssetUrl(ship.preview_url) : null;
                    return (
                      <div
                        key={ship.ship_id}
                        className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3 flex gap-3 items-center"
                      >
                        {preview ? (
                          <img
                            src={preview}
                            alt={ship.ship_id}
                            className="w-16 h-12 object-cover rounded-lg bg-black shrink-0"
                          />
                        ) : (
                          <div className="w-16 h-12 rounded-lg bg-gray-100 dark:bg-white/5 shrink-0" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-mono font-semibold truncate">{ship.ship_id}</p>
                          <p className="text-xs text-gray-500">
                            {ship.similarity_percent.toFixed(1)}% · {ship.hit_count} hit(s) · mean score{' '}
                            {ship.aggregated_score.toFixed(3)}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
