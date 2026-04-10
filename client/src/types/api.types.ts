export type UserRead = {
  id: string;
  email: string;
  full_name: string;
  role_id: string;
  is_active: boolean;
  role?: RoleRead;
}

export type RoleRead = {
  id: string;
  role_name?: string;
  name?: string;
  description?: string;
}

export type VesselTypeRead = {
  id: string;
  name: string;
  description?: string;
}

export type VesselRead = {
  id: string;
  ship_id: string;
  name: string;
  vessel_type_id: string;
  owner_info?: string;
  is_active: boolean;
  vessel_type?: VesselTypeRead;
}

export type DetectionRead = {
  id: string;
  vessel_id?: string | null;
  track_id?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  created_at: string;
  confidence?: number | null;
  is_accepted?: boolean | null;
  ocr_results?: Array<Record<string, unknown>> | null;
  vessel?: VesselRead;
}

export type OrderRead = {
  id: string;
  vessel_id: string;
  cargo_details?: string;
  status: 'pending' | 'processing' | 'completed' | 'cancelled';
  total_amount: number;
  created_at: string;
  vessel?: VesselRead;
}

export type InvoiceRead = {
  id: string;
  order_id: string;
  invoice_number: string;
  total_amount: number;
  tax_amount: number;
  payment_status: 'unpaid' | 'partial' | 'paid';
  created_at: string;
}

export type DashboardStats = {
  total_vessels: number;
  detections_today: number;
  pending_orders: number;
  unpaid_invoices_count: number;
  active_cameras: number;
  total_revenue: number;
}

export type CameraRead = {
  id: string;
  camera_name: string;
  name?: string;
  rtsp_url: string;
  is_active: boolean;
}

export type PortLogRead = {
  id: string;
  ship_id: string;
  log_date: string;
  event_type: string;
  details?: string;
}

export type AuditLogRead = {
  id: string;
  user_id: string;
  action: string;
  table_name: string;
  record_id: string;
  created_at: string;
  user?: UserRead;
}
