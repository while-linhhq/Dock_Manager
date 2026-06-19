import React, { useCallback, useRef, useState } from 'react';
import { ImagePlus } from 'lucide-react';
import { cn } from '../../../utils/cn';

type FileDropzoneProps = {
  accept: string;
  allowedExtensions: string[];
  file: File | null;
  onFileChange: (file: File | null) => void;
  emptyTitle: string;
  emptyHint: string;
  accent?: 'blue' | 'violet';
  className?: string;
};

function isAllowedFile(file: File, allowedExtensions: string[]): boolean {
  const name = file.name.toLowerCase();
  if (allowedExtensions.some((ext) => name.endsWith(ext))) {
    return true;
  }
  const mime = file.type.toLowerCase();
  if (mime.startsWith('image/') && allowedExtensions.some((e) => ['.jpg', '.jpeg', '.png', '.webp', '.bmp'].includes(e))) {
    return true;
  }
  if (mime.startsWith('video/') && allowedExtensions.some((e) => ['.mp4', '.webm', '.mov', '.avi', '.mkv'].includes(e))) {
    return true;
  }
  return false;
}

export const FileDropzone: React.FC<FileDropzoneProps> = ({
  accept,
  allowedExtensions,
  file,
  onFileChange,
  emptyTitle,
  emptyHint,
  accent = 'blue',
  className,
}) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [rejectMessage, setRejectMessage] = useState<string | null>(null);

  const pickFile = useCallback(
    (picked: File | null) => {
      setRejectMessage(null);
      if (!picked) {
        onFileChange(null);
        return;
      }
      if (!isAllowedFile(picked, allowedExtensions)) {
        setRejectMessage(`Định dạng không hỗ trợ: ${picked.name}`);
        return;
      }
      onFileChange(picked);
    },
    [allowedExtensions, onFileChange],
  );

  const onDragEnter = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(true);
  };

  const onDragOver = (event: React.DragEvent) => {
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
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    const dropped = event.dataTransfer.files?.[0] ?? null;
    pickFile(dropped);
  };

  const borderAccent =
    accent === 'violet'
      ? 'border-violet-500/60 bg-violet-500/5'
      : 'border-blue-500/60 bg-blue-500/5';

  const iconAccent = accent === 'violet' ? 'text-violet-500' : 'text-blue-500';

  return (
    <div className={cn('flex-1', className)}>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
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
          'cursor-pointer rounded-xl border border-dashed px-4 py-8 transition-colors',
          'border-gray-300 dark:border-white/15 bg-gray-50/80 dark:bg-white/[0.02]',
          accent === 'violet' ? 'hover:border-violet-500/40' : 'hover:border-blue-500/40',
          isDragging && borderAccent,
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(event) => pickFile(event.target.files?.[0] ?? null)}
        />
        <div className="flex flex-col items-center justify-center gap-2 text-center text-gray-600 dark:text-gray-300">
          <ImagePlus className={cn('h-8 w-8', iconAccent, isDragging && 'scale-110 transition-transform')} />
          <div>
            <p className="text-sm font-medium">
              {file ? file.name : emptyTitle}
            </p>
            <p className="mt-1 text-[11px] text-gray-500">
              {isDragging ? 'Thả file vào đây…' : emptyHint}
            </p>
          </div>
        </div>
      </div>
      {rejectMessage ? (
        <p className="mt-2 text-xs text-red-500">{rejectMessage}</p>
      ) : null}
    </div>
  );
};
