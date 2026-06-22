export interface PatternRead {
  id: number;
  name: string;
  pattern: string;
  priority: number;
  description: string | null;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface PatternCreate {
  name: string;
  pattern: string;
  priority: number;
  description?: string;
  is_active: boolean;
}

export interface PatternUpdate {
  name?: string;
  pattern?: string;
  priority?: number;
  description?: string;
  is_active?: boolean;
}

export interface BlacklistRead {
  id: number;
  value: string;
  reason: string | null;
  created_at: string | null;
}

export interface BlacklistCreate {
  value: string;
  reason?: string;
}

export interface ConvertMapRead {
  id: number;
  wrong_value: string;
  correct_value: string;
  reason: string | null;
  created_at: string | null;
}

export interface ConvertMapCreate {
  wrong_value: string;
  correct_value: string;
  reason?: string;
}

export interface ConvertMapUpdate {
  correct_value?: string;
  reason?: string;
}
