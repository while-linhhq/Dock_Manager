import { z } from 'zod';

export const vesselClassificationEnum = z.enum(['spot', 'monthly', 'unclassified']);

export const vesselSchema = z
  .object({
    ship_id: z.string().min(1, 'Mã tàu là bắt buộc'),
    name: z.string().min(1, 'Tên tàu là bắt buộc'),
    classification: vesselClassificationEnum.optional(),
    vessel_type_id: z.string().optional(),
    owner_info: z.string().optional(),
    length_m: z
      .string()
      .optional()
      .refine((value) => !value || Number(value) >= 0, 'Chiều dài phải lớn hơn hoặc bằng 0'),
    registry_expiry: z.string().optional(),
    is_active: z.boolean().optional(),
  })
  .refine(
    (data) => data.classification !== 'monthly' || Boolean(data.vessel_type_id),
    { path: ['vessel_type_id'], message: 'Tàu tháng bắt buộc chọn loại tàu' },
  );

export const vesselTypeSchema = z.object({
  type_name: z.string().min(1, 'Tên loại tàu là bắt buộc'),
  description: z.string().optional(),
  // Danh sách id tàu (tháng) gán cho loại này. Gửi kèm khi tạo/sửa loại.
  member_vessel_ids: z.array(z.number()).optional(),
});
