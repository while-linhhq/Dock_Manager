import { z } from 'zod';

export const cameraSchema = z.object({
  name: z.string().min(1, 'Tên camera là bắt buộc'),
  rtsp_url: z.string().url('URL RTSP không hợp lệ'),
  is_active: z.boolean().default(true),
});

export const configSchema = z.object({
  key: z.string().min(1, 'Key không được để trống'),
  value: z.string().min(1, 'Giá trị không được để trống'),
  description: z.string().optional(),
});

export const pipelineSchema = z.object({
  source: z.string().optional(),
  enable_ocr: z.boolean().default(true),
});
