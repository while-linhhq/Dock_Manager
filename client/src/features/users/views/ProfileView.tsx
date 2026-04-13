import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Save } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { usersApi } from '../services/usersApi';
import { useAuthStore } from '../../auth/store/authStore';

const profileSchema = z.object({
  full_name: z.string().min(1, 'Họ tên là bắt buộc'),
  email: z.string().email('Email không hợp lệ'),
  phone: z.string().optional(),
  password: z.string().min(6, 'Mật khẩu ít nhất 6 ký tự').optional().or(z.literal('')),
});

type ProfileFormValues = z.infer<typeof profileSchema>;

export const ProfileView: React.FC = () => {
  const { user, setUserProfile } = useAuthStore();
  const [isSaving, setIsSaving] = React.useState(false);
  const [status, setStatus] = React.useState<string>('');

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      full_name: user?.full_name ?? '',
      email: user?.email ?? '',
      phone: user?.phone ?? '',
      password: '',
    },
  });

  React.useEffect(() => {
    form.reset({
      full_name: user?.full_name ?? '',
      email: user?.email ?? '',
      phone: user?.phone ?? '',
      password: '',
    });
  }, [form, user]);

  const onSubmit = async (values: ProfileFormValues) => {
    try {
      setIsSaving(true);
      setStatus('');
      const payload: { full_name?: string; email?: string; phone?: string; password?: string } = {
        full_name: values.full_name,
        email: values.email,
        phone: values.phone || undefined,
      };
      if (values.password && values.password.trim().length > 0) {
        payload.password = values.password.trim();
      }
      const updated = await usersApi.updateMe(payload);
      setUserProfile(updated);
      form.reset({ ...values, password: '' });
      setStatus('Đã cập nhật thông tin cá nhân');
    } catch (error) {
      console.error(error);
      setStatus('Cập nhật thất bại');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-lg font-bold uppercase tracking-wider text-gray-900 dark:text-white">
          Hồ Sơ Cá Nhân
        </h2>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Chỉnh sửa thông tin người dùng và đổi mật khẩu.
        </p>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-xl dark:border-white/10 dark:bg-[#121214]">
        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <Input
            label="Họ và tên"
            {...form.register('full_name')}
            error={form.formState.errors.full_name?.message}
          />
          <Input
            label="Email"
            type="email"
            {...form.register('email')}
            error={form.formState.errors.email?.message}
          />
          <Input label="Số điện thoại" {...form.register('phone')} />
          <Input
            label="Mật khẩu mới (không bắt buộc)"
            type="password"
            {...form.register('password')}
            error={form.formState.errors.password?.message}
          />

          <div className="flex items-center justify-between pt-2">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{status}</span>
            <Button
              type="submit"
              disabled={isSaving}
              className="bg-blue-600 text-white hover:bg-blue-700"
            >
              <Save className="mr-2 h-4 w-4" />
              {isSaving ? 'Đang lưu...' : 'Lưu thay đổi'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
