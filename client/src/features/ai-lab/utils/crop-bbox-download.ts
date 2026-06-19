type Bbox = [number, number, number, number];

function clampBox(box: Bbox, frameW: number, frameH: number) {
  const x1 = Math.max(0, Math.min(frameW - 1, Math.floor(box[0])));
  const y1 = Math.max(0, Math.min(frameH - 1, Math.floor(box[1])));
  const x2 = Math.max(x1 + 1, Math.min(frameW, Math.ceil(box[2])));
  const y2 = Math.max(y1 + 1, Math.min(frameH, Math.ceil(box[3])));
  return { x1, y1, width: x2 - x1, height: y2 - y1 };
}

function loadImageCanvas(file: File): Promise<HTMLCanvasElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');
      URL.revokeObjectURL(url);
      if (!ctx) {
        reject(new Error('Không khởi tạo được canvas'));
        return;
      }
      ctx.drawImage(img, 0, 0);
      resolve(canvas);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Không đọc được ảnh'));
    };
    img.src = url;
  });
}

function loadVideoFrameCanvas(file: File, timeSec: number): Promise<HTMLCanvasElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement('video');
    video.preload = 'auto';
    video.muted = true;
    video.playsInline = true;
    video.src = url;

    const cleanup = () => URL.revokeObjectURL(url);

    video.onloadedmetadata = () => {
      const duration = Number.isFinite(video.duration) ? video.duration : timeSec;
      const target = Math.max(0, Math.min(timeSec, Math.max(0, duration - 0.05)));
      video.currentTime = target;
    };

    video.onseeked = () => {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      cleanup();
      if (!ctx || canvas.width === 0 || canvas.height === 0) {
        reject(new Error('Không đọc được frame video'));
        return;
      }
      ctx.drawImage(video, 0, 0);
      resolve(canvas);
    };

    video.onerror = () => {
      cleanup();
      reject(new Error('Không đọc được video'));
    };
  });
}

function triggerDownload(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

function canvasToJpegBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error('Xuất ảnh thất bại'));
          return;
        }
        resolve(blob);
      },
      'image/jpeg',
      0.92,
    );
  });
}

function buildCropFilename(
  sourceFilename: string,
  trackId: string,
  frameIndex: number,
): string {
  const stem = sourceFilename.replace(/\.[^.]+$/, '') || 'lab';
  const safeTrack = trackId.replace(/[^\w.-]+/g, '_');
  return `${stem}_track-${safeTrack}_frame-${frameIndex}.jpg`;
}

export async function cropBboxAndDownload(options: {
  file: File;
  mediaType: 'image' | 'video';
  box: Bbox;
  timeSec?: number;
  frameIndex?: number;
  sourceFilename: string;
  trackId: string;
}): Promise<void> {
  const { file, mediaType, box, sourceFilename, trackId } = options;
  const frameIndex = options.frameIndex ?? 0;
  const timeSec = options.timeSec ?? 0;

  const sourceCanvas =
    mediaType === 'video'
      ? await loadVideoFrameCanvas(file, timeSec)
      : await loadImageCanvas(file);

  const { x1, y1, width, height } = clampBox(
    box,
    sourceCanvas.width,
    sourceCanvas.height,
  );

  const cropCanvas = document.createElement('canvas');
  cropCanvas.width = width;
  cropCanvas.height = height;
  const ctx = cropCanvas.getContext('2d');
  if (!ctx) {
    throw new Error('Không khởi tạo được canvas');
  }
  ctx.drawImage(sourceCanvas, x1, y1, width, height, 0, 0, width, height);

  const blob = await canvasToJpegBlob(cropCanvas);
  triggerDownload(blob, buildCropFilename(sourceFilename, trackId, frameIndex));
}
