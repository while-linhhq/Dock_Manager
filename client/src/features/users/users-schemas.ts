import { z } from 'zod';

const userBaseSchema = z.object({
  username: z.string().trim().min(3, 'Username ít nhất 3 ký tự').optional(),
  email: z.string().email('Email không hợp lệ'),
  password: z
    .string()
    .min(6, 'Mật khẩu ít nhất 6 ký tự')
    .refine((value) => value.trim().length > 0, 'Mật khẩu không được chỉ chứa khoảng trắng')
    .optional(),
  full_name: z.string().min(1, 'Họ tên là bắt buộc'),
  role_id: z.string().min(1, 'Vai trò là bắt buộc'),
  is_active: z.boolean().optional(),
});

export const userCreateSchema = userBaseSchema.superRefine((data, ctx) => {
  if (!data.username) {
    ctx.addIssue({ code: 'custom', path: ['username'], message: 'Username là bắt buộc' });
  }
  if (!data.password) {
    ctx.addIssue({ code: 'custom', path: ['password'], message: 'Mật khẩu là bắt buộc' });
  }
});

export const userUpdateSchema = userBaseSchema;

export const roleSchema = z.object({
  role_name: z.string().min(1, 'Tên vai trò là bắt buộc'),
  description: z.string().optional(),
  permissions: z
    .object({
      all: z.boolean().optional(),
      menus: z.array(z.string()).optional(),
    })
    .optional(),
});

export type UserFormValues = z.infer<typeof userBaseSchema>;
