export interface PrivacyConfiguration {
  notice: {
    version: string;
    personal_data: Array<{ item: string; detail: string }>;
    purposes: string[];
    what_does_not_happen: string[];
    known_exceptions: string[];
  };
  data_fiduciary: string | null;
  grievance: {
    configured: boolean;
    name: string | null;
    email: string | null;
    phone: string | null;
    address: string | null;
  };
  retention: { chat_retention_days: number; chats_kept_until_deleted: boolean };
  self_service_reset: boolean;
}

export interface ConsentState {
  current_version: string;
  accepted_version: string | null;
  accepted_at: string | null;
  withdrawn_at: string | null;
  required: boolean;
}

export interface AccountStatus {
  mfa_enabled: boolean;
  mfa_pending: boolean;
  recovery_codes_remaining: number;
  must_change_password: boolean;
  password_changed_at: string | null;
  consent: ConsentState;
}

export interface DeviceSession {
  id: string;
  label: string;
  created_at: string;
  last_seen_at: string;
  current: boolean;
}

export interface StepUp {
  password: string;
  mfa_code?: string;
  recovery_code?: string;
}

export interface ErasureReceipt {
  receipt_id: string;
  counts: Record<string, number>;
}

export interface HistorySession {
  id: string;
  title: string;
  case_id: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview: string | null;
  pinned: boolean;
  matter: string | null;
  match_snippet: string | null;
}

export interface HistoryPage {
  items: HistorySession[];
  next_cursor: string | null;
}

export interface MatterCount {
  matter: string;
  count: number;
}

export interface RetentionStatus {
  chat_retention_days: number;
  chats_kept_until_deleted: boolean;
  conversations_past_retention: number;
}

export interface AdminResetCode {
  code: string;
  expires_at: string;
  mfa_cleared: boolean;
}
