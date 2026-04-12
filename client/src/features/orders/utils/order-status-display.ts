export const statusColors: Record<string, string> = {
  processing: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  completed: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  pending: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  cancelled: 'text-red-500 bg-red-500/10 border-red-500/20',
};

export const statusLabels: Record<string, string> = {
  processing: 'Đang Xử Lý',
  completed: 'Hoàn Thành',
  pending: 'Chờ Duyệt',
  cancelled: 'Đã Hủy',
};

export function normOrderStatus(status: string) {
  const s = status.toLowerCase();
  return s in statusLabels ? s : 'pending';
}
