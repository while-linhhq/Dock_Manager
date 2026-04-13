import React from 'react';
import {
  ShipWheel,
} from 'lucide-react';
import type { DashboardSystemOverview } from '../../../types/api.types';
import { cn } from '../../../utils/cn';

type WidgetProps = {
  label: string;
  value: number;
  hint: string;
  color: string;
};

const Widget: React.FC<WidgetProps> = ({ label, value, hint, color }) => (
  <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4 shadow-lg">
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
        <p className="mt-1 text-2xl font-extrabold tracking-tight text-gray-900 dark:text-white">
          {value.toLocaleString('vi-VN')}
        </p>
        <p className="mt-1 text-[10px] font-mono uppercase tracking-wide text-gray-500">{hint}</p>
      </div>
      <span className={cn('h-2.5 w-2.5 rounded-full mt-2 shrink-0', color)} />
    </div>
  </div>
);

export type DashboardSystemOverviewWidgetsProps = {
  data: DashboardSystemOverview | null;
  isLoading: boolean;
};

export const DashboardSystemOverviewWidgets: React.FC<DashboardSystemOverviewWidgetsProps> = ({
  data,
  isLoading,
}) => {
  if (isLoading && !data) {
    return (
      <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-6">
        <p className="text-xs font-bold uppercase tracking-widest text-gray-500">
          Tổng quan vận hành cảng
        </p>
        <p className="mt-2 text-sm text-gray-500">Đang tải dữ liệu hệ thống...</p>
      </div>
    );
  }

  const d = data;
  if (!d) {
    return null;
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2 text-gray-700 dark:text-gray-200">
        <ShipWheel className="h-4 w-4 text-blue-500" />
        <h3 className="text-xs font-bold uppercase tracking-widest">Tổng quan vận hành cảng</h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <Widget
          label="Đăng ký tàu hôm nay"
          value={d.registered_vessels_day}
          hint="Theo ngày (VN)"
          color="bg-blue-500"
        />
        <Widget
          label="Đăng ký tàu tháng này"
          value={d.registered_vessels_month}
          hint="Theo tháng (VN)"
          color="bg-indigo-500"
        />
        <Widget
          label="Đăng ký tàu năm nay"
          value={d.registered_vessels_year}
          hint="Theo năm (VN)"
          color="bg-violet-500"
        />
        <Widget
          label="Tàu không tính phí"
          value={d.vessels_no_fee}
          hint="Không có cấu hình billable"
          color="bg-amber-500"
        />
        <Widget
          label="Loại tàu thiếu phí active"
          value={d.vessel_types_without_active_fee}
          hint={`Tổng loại tàu: ${d.total_vessel_types.toLocaleString('vi-VN')}`}
          color="bg-rose-500"
        />
        <Widget
          label="Camera đang hoạt động"
          value={d.active_cameras}
          hint={`Ngừng hoạt động: ${d.inactive_cameras.toLocaleString('vi-VN')}`}
          color="bg-emerald-500"
        />
        <Widget
          label="Tàu có thể thu phí"
          value={d.vessels_billable}
          hint={`Tổng đăng ký: ${d.total_registered_vessels.toLocaleString('vi-VN')}`}
          color="bg-cyan-500"
        />
        <Widget
          label="Hóa đơn AI đã tạo"
          value={d.ai_invoices}
          hint={`Hóa đơn chưa thanh toán: ${d.unpaid_invoices.toLocaleString('vi-VN')}`}
          color="bg-fuchsia-500"
        />
        <Widget
          label="Đơn hàng chờ xử lý"
          value={d.pending_orders}
          hint={`Tàu chưa gán loại: ${d.vessels_without_type.toLocaleString('vi-VN')}`}
          color="bg-lime-500"
        />
      </div>
    </section>
  );
};
