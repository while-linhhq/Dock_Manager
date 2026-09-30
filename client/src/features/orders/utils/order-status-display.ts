// Bốn nhãn cũ gồm 'processing' — thực chất server chuẩn hoá 'processing' về
// 'PENDING' (`normalize_order_status`), nên bộ lọc và form tạo đơn có một lựa
// chọn trùng với "Chờ Duyệt" mà không bao giờ hiển thị được. Bỏ hẳn để danh sách
// lựa chọn khớp đúng ba trạng thái thật trong DB (PENDING/COMPLETED/CANCELLED).
export const statusColors: Record<string, string> = {
  completed: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  pending: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  cancelled: 'text-red-500 bg-red-500/10 border-red-500/20',
};

export const statusLabels: Record<string, string> = {
  pending: 'Chờ Duyệt',
  completed: 'Hoàn Thành',
  cancelled: 'Đã Hủy',
};

export function normOrderStatus(status: string) {
  const s = status.toLowerCase();
  // Own-property check: `s in statusLabels` đi cả prototype chain, nên một trạng
  // thái lạ như 'constructor'/'toString' lọt qua và `statusLabels[st]` trả về
  // function — React nhận function làm child và `statusColors[st]` nhét function
  // vào className. Chỉ ba khóa thật của statusLabels mới được coi là hợp lệ.
  return Object.prototype.hasOwnProperty.call(statusLabels, s) ? s : 'pending';
}
