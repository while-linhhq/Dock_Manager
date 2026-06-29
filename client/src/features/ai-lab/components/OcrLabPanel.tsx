import React, { useState } from 'react';
import { Loader2, ScanText } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { FileDropzone } from './FileDropzone';
import { aiLabApi } from '../services/aiLabApi';
import type { LabOcrResponse } from '../types/ai-lab.types';

const ACCEPT = 'image/jpeg,image/png,image/webp';
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp'];

export const OcrLabPanel: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LabOcrResponse | null>(null);

  const onPickFile = (picked: File | null) => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setFile(picked);
    setResult(null);
    setError(null);
    setPreviewUrl(picked ? URL.createObjectURL(picked) : null);
  };

  const runOcr = async () => {
    if (!file) {
      return;
    }
    setIsRunning(true);
    setError(null);
    try {
      const response = await aiLabApi.runOcr(file);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chạy OCR thất bại');
      setResult(null);
    } finally {
      setIsRunning(false);
    }
  };

  const previewSrc =
    result?.jpeg_base64 != null
      ? `data:image/jpeg;base64,${result.jpeg_base64}`
      : previewUrl;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-5 space-y-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
            Test OCR (pipeline service)
          </h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Upload ảnh crop biển số hoặc vùng chữ — dùng cùng PaddleOCR + rule engine như pipeline live.
          </p>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <FileDropzone
            accept={ACCEPT}
            allowedExtensions={ALLOWED_EXTENSIONS}
            file={file}
            onFileChange={onPickFile}
            emptyTitle="Kéo thả ảnh OCR vào đây"
            emptyHint="hoặc bấm để chọn · jpg, png, webp"
            accent="blue"
          />

          <Button
            type="button"
            onClick={() => void runOcr()}
            disabled={!file || isRunning}
            className="inline-flex items-center gap-2"
          >
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanText className="h-4 w-4" />}
            Chạy OCR
          </Button>
        </div>

        {error ? <p className="text-xs text-red-500">{error}</p> : null}
      </div>

      {result ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] overflow-hidden">
            {previewSrc ? (
              <img
                src={previewSrc}
                alt="OCR input"
                className="w-full max-h-[min(72vh,840px)] object-contain bg-black"
              />
            ) : null}
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4 text-xs font-mono space-y-1 text-gray-600 dark:text-gray-300">
              <p>File: {result.filename}</p>
              <p>
                Kích thước: {result.image_size.width}×{result.image_size.height}
              </p>
              <p>Device: {result.ocr_device ?? '—'}</p>
              <p>Thời gian: {result.processing_ms.toFixed(1)} ms</p>
              <p>
                Kết quả:{' '}
                {result.matched ? (
                  <span className="text-emerald-600 dark:text-emerald-400">
                    {result.ship_ids.length} mã tàu
                  </span>
                ) : (
                  <span className="text-amber-600 dark:text-amber-400">không khớp pattern</span>
                )}
              </p>
            </div>

            {result.ship_ids.length > 0 ? (
              <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4 space-y-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                  Mã tàu nhận diện
                </p>
                <ul className="space-y-2">
                  {result.ship_ids.map((item, index) => (
                    <li
                      key={`${item.id}-${index}`}
                      className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2"
                    >
                      <p className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
                        {item.id}
                      </p>
                      <p className="text-[11px] text-gray-500 mt-0.5">
                        confidence {(item.confidence * 100).toFixed(1)}%
                        {item.raw_text ? ` · raw: ${item.raw_text}` : ''}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 text-xs text-amber-800 dark:text-amber-200">
                PaddleOCR chạy xong nhưng không trích được mã tàu theo rule engine. Thử crop sát biển số,
                tăng độ phân giải, hoặc kiểm tra pattern trong Cấu hình mã tàu.
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
};
