export type UserRead = {
  id: string;
  username?: string;
  email: string;
  full_name: string;
  phone?: string | null;
  role_id: string;
  is_active: boolean;
  role?: RoleRead;
}

export type RoleRead = {
  id: string;
  role_name?: string;
  name?: string;
  description?: string;
  permissions?: Record<string, unknown> | null;
}

export type VesselTypeRead = {
  id: string;
  type_name: string;
  description?: string | null;
  created_at?: string;
}

export type ApplicableFeeRead = {
  fee_name: string;
  base_fee: number | string;
  unit?: string | null;
}

export type VesselRead = {
  id: string | number;
  ship_id: string;
  name?: string | null;
  vessel_type_id?: string | number | null;
  /** Backend field */
  owner?: string | null;
  /** Legacy / form alias */
  owner_info?: string | null;
  registration_number?: string | null;
  is_active: boolean;
  vessel_type?: VesselTypeRead;
  /** First active fee config for this vessel's type */
  applicable_fee?: ApplicableFeeRead | null;
  last_seen?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type DetectionRead = {
  id: string;
  vessel_id?: string | null;
  track_id?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  video_path?: string | null;
  video_url?: string | null;
  audit_image_path?: string | null;
  audit_image_url?: string | null;
  created_at: string;
  confidence?: number | null;
  is_accepted?: boolean | null;
  ocr_results?: Array<Record<string, unknown>> | null;
  vessel?: VesselRead;
}

export type DetectionMediaRead = {
  id: number;
  detection_id: number;
  media_type: 'image' | 'video' | 'thumbnail' | string;
  file_path: string;
  file_size?: number | null;
  created_at: string;
};

export type OrderRead = {
  id: number | string;
  order_number?: string;
  vessel_id?: number | string | null;
  cargo_details?: string;
  status: string;
  total_amount?: number | string;
  created_at: string;
  /** API joined-load từ orders list/detail */
  vessel?: Pick<VesselRead, 'id' | 'ship_id' | 'name'> | null;
}

export type InvoiceLineItemRead = {
  id?: number;
  fee_config_id?: number | null;
  description?: string | null;
  quantity?: number | string | null;
  unit_price?: number | string;
  amount?: number | string;
  fee_config?: { fee_name?: string; unit?: string | null } | null;
};

export type InvoiceRead = {
  id: number | string;
  order_id?: number | string | null;
  vessel_id?: number | string | null;
  detection_id?: number | string | null;
  invoice_number: string;
  subtotal?: number | string | null;
  total_amount: number | string;
  tax_amount?: number | string;
  payment_status: string;
  created_at: string;
  deleted_at?: string | null;
  items?: InvoiceLineItemRead[];
  creation_source?: string;
  /** Backend computed: "AI" | tên/email user | "—" */
  created_by_label?: string;
  vessel_ship_id?: string | null;
  vessel_type_name?: string | null;
  detection_confidence_avg?: number | string | null;
  berth_duration_hours?: number | string | null;
  berth_duration_seconds?: number | null;
};

export type FeeConfigRead = {
  id: number;
  vessel_type_id?: number | null;
  fee_name: string;
  base_fee: number | string;
  unit?: string | null;
  is_active: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  created_at: string;
  updated_at: string;
  vessel_type?: VesselTypeRead;
}

export type PaymentRead = {
  id: number;
  invoice_id: number;
  amount: number | string;
  payment_method?: string | null;
  payment_reference?: string | null;
  notes?: string | null;
  paid_at: string;
  created_by?: number | null;
  created_at: string;
}

/** Khớp GET /dashboard/stats (snake_case từ API) */
export type DashboardStats = {
  total_vessels: number;
  total_detections_today: number;
  pending_orders: number;
  completed_orders_today: number;
  total_revenue_today: number | string;
  unpaid_invoices: number;
  active_cameras: number;
};

export type DashboardPeriod = 'day' | 'month' | 'year';

export type DashboardSystemOverview = {
  registered_vessels_day: number;
  registered_vessels_month: number;
  registered_vessels_year: number;
  total_registered_vessels: number;
  vessels_without_type: number;
  vessels_no_fee: number;
  vessels_billable: number;
  total_vessel_types: number;
  vessel_types_without_active_fee: number;
  active_cameras: number;
  inactive_cameras: number;
  pending_orders: number;
  unpaid_invoices: number;
  ai_invoices: number;
};

export type DashboardSummary = {
  period: DashboardPeriod;
  period_start: string;
  period_end: string;
  distinct_ships_detected: number;
  transient_fee_revenue: number | string;
  auto_invoices_created: number;
  pending_orders: number;
  revenue_chart_labels: string[];
  revenue_chart_totals: number[];
  revenue_chart_ai: number[];
  revenue_chart_manual: number[];
  top_ship_labels: string[];
  top_ship_counts: number[];
  /** Trong kỳ (ngày/tháng/năm), múi giờ VN — khớp bộ lọc dashboard */
  detections_review_accepted: number;
  detections_review_not_accepted: number;
  detections_review_unassigned: number;
  /** Trục thời gian lượt nhận diện theo kỳ (giờ / ngày / tháng); thiếu → FE fallback 24h */
  detection_volume_labels?: string[];
  detection_volume_counts?: number[];
};

export type CameraRead = {
  id: string;
  camera_name: string;
  name?: string;
  rtsp_url: string;
  is_active: boolean;
}

export type PortLogRead = {
  id: number | string;
  seq?: number | null;
  ships_completed_today?: number | null;
  logged_at?: string | null;
  track_id?: string | null;
  voted_ship_id?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  confidence?: number | null;
  ocr_attempts?: number | null;
  vote_summary?: Record<string, unknown> | null;
  schema_version?: number;
  /** Legacy / export aliases */
  ship_id?: string;
  log_date?: string;
  event_type?: string;
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
