import React, { useCallback, useRef, useState } from 'react';
import { ImagePlus } from 'lucide-react';
import { cn } from '../../utils/cn';

const DEFAULT_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'];

type ImageMultiDropzoneProps = {
  files: File[];
  onFilesChange: (files: File[]) => void;
  accept?: string;
  allowedExtensions?: string[];
  emptyTitle?: string;
  emptyHint?: string;
  disabled?: boolean;
  className?: string;
};

function isAllowedImage(file: File, allowedExtensions: string[]): boolean {
  const name = file.name.toLowerCase();
  if (allowedExtensions.some((ext) => name.endsWith(ext))) {
    return true;
  }
  return file.type.toLowerCase().startsWith('image/');
}

function mergeFiles(existing: File[], incoming: File[]): File[] {
  const key = (file: File) => `${file.name}-${file.size}-${file.lastModified}`;
  const seen = new Set(existing.map(key));
  const next = [...existing];
  for (const file of incoming) {
    const fileKey = key(file);
    if (!seen.has(fileKey)) {
      seen.add(fileKey);
      next.push(file);
    }
  }
  return next;
}

export const ImageMultiDropzone: React.FC<ImageMultiDropzoneProps> = ({
  files,
  onFilesChange,
  accept = 'image/*',
  allowedExtensions = DEFAULT_EXTENSIONS,
  emptyTitle = 'Kéo thả ảnh vào đây',
  emptyHint = 'hoặc bấm để chọn một hoặc nhiều ảnh (jpg, png, webp…)',
  disabled = false,
  className,
}) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [rejectMessage, setRejectMessage] = useState<string | null>(null);

  const pickFiles = useCallback(
    (picked: FileList | File[] | null, mode: 'replace' | 'append' = 'append') => {
      setRejectMessage(null);
      if (!picked || picked.length === 0) {
        if (mode === 'replace') {
          onFilesChange([]);
        }
        return;
      }

      const valid: File[] = [];
      const rejected: string[] = [];
      Array.from(picked).forEach((file) => {
        if (isAllowedImage(file, allowedExtensions)) {
          valid.push(file);
        } else {
          rejected.push(file.name);
        }
      });

      if (rejected.length > 0) {
        setRejectMessage(`Bỏ qua ${rejected.length} file không phải ảnh: ${rejected.join(', ')}`);
      }

      if (valid.length === 0) {
        return;
      }

      const next = mode === 'replace' ? valid : mergeFiles(files, valid);
      onFilesChange(next);
    },
    [allowedExtensions, files, onFilesChange],
  );

  const onDragEnter = (event: React.DragEvent) => {
    if (disabled) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(true);
  };

  const onDragOver = (event: React.DragEvent) => {
    if (disabled) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';
    setIsDragging(true);
  };

  const onDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const next = event.relatedTarget as Node | null;
    if (next && event.currentTarget.contains(next)) {
      return;
    }
    setIsDragging(false);
  };

  const onDrop = (event: React.DragEvent) => {
    if (disabled) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    pickFiles(event.dataTransfer.files, 'append');
  };

  const title =
    files.length > 0 ? `Đã chọn ${files.length} ảnh` : emptyTitle;

  return (
    <div className={className}>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        onClick={() => {
          if (!disabled) {
            inputRef.current?.click();
          }
        }}
        onKeyDown={(event) => {
          if (disabled) {
            return;
          }
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          'rounded-xl border-2 border-dashed px-4 py-6 transition-colors',
          'border-gray-300 dark:border-white/15 bg-gray-50/50 dark:bg-white/[0.02]',
          !disabled && 'cursor-pointer hover:border-blue-500/60',
          disabled && 'cursor-not-allowed opacity-60',
          isDragging && !disabled && 'border-blue-500/70 bg-blue-500/5',
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple
          disabled={disabled}
          className="hidden"
          onChange={(event) => {
            pickFiles(event.target.files, 'append');
            event.target.value = '';
          }}
        />
        <div className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-200">
          <ImagePlus
            className={cn(
              'h-5 w-5 shrink-0 text-blue-500',
              isDragging && !disabled && 'scale-110 transition-transform',
            )}
          />
          <div>
            <p className="font-medium">{isDragging && !disabled ? 'Thả ảnh vào đây…' : title}</p>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{emptyHint}</p>
          </div>
        </div>
      </div>
      {rejectMessage ? (
        <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">{rejectMessage}</p>
      ) : null}
    </div>
  );
};
