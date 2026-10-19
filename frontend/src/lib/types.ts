export type Role = "owner" | "admin" | "technician" | "member" | "viewer";
export const ROLE_RANK: Record<Role, number> = { viewer: 0, member: 1, technician: 2, admin: 3, owner: 4 };
export const ROLES: Role[] = ["owner", "admin", "technician", "member", "viewer"];

export interface OrgM { id: string; name: string; slug: string; role: Role }
export interface Me { id: string; email: string; name: string; is_superuser: boolean; mfa_enabled: boolean; must_change_password: boolean; organizations: OrgM[] }
export interface UserBrief { id: string; name: string; email: string }
export interface Member { user_id: string; name: string; email: string; role: Role; mfa_enabled: boolean; is_active: boolean; last_login_at: string | null }

export interface Ticket {
  id: string; number: number; key: string; title: string; description: string; priority: "P1" | "P2" | "P3" | "P4";
  status: "open" | "in_progress" | "waiting" | "resolved" | "closed"; requester: UserBrief | null; assignee: UserBrief | null;
  asset_id: string | null; created_at: string; updated_at: string; resolved_at: string | null;
}
export interface Comment { id: string; author: UserBrief | null; body: string; internal: boolean; created_at: string }
export interface TicketDetail extends Ticket { comments: Comment[] }

export interface Asset {
  id: string; tag: string; name: string; asset_type: string; os: string; assigned_to: UserBrief | null; location: string;
  status: "in_stock" | "in_service" | "repair" | "retired"; serial_number: string; purchase_date: string | null;
  warranty_end: string | null; warranty_expiring: boolean; notes: string; open_tickets: number;
}

export interface Doc { id: string; filename: string; size_bytes: number; status: "processing" | "indexed" | "failed"; error: string; chunk_count: number; uploaded_by: UserBrief | null; created_at: string; sha256: string }
export interface MemoryEntry { id: string; title: string; content: string; updated_at: string }
export interface Citation { n: number; document_id: string; filename: string; page: number | null; excerpt: string }
export interface Message { id: string; role: "user" | "assistant"; content: string; citations: Citation[]; model: string; created_at: string }
export interface Conversation { id: string; title: string; updated_at: string }

export const STATUS_LABEL: Record<Ticket["status"], string> = { open: "Open", in_progress: "In progress", waiting: "Waiting", resolved: "Resolved", closed: "Closed" };
export const STATUS_CLASS: Record<Ticket["status"], string> = { open: "info", in_progress: "warn", waiting: "mute", resolved: "ok", closed: "mute" };
export const PRIORITY_CLASS = { P1: "crit", P2: "warn", P3: "info", P4: "mute" } as const;
export const ASSET_STATUS: Record<Asset["status"], [string, string]> = {
  in_stock: ["In stock", "mute"], in_service: ["In service", "ok"], repair: ["In repair", "warn"], retired: ["Retired", "mute"],
};

// ---- 3.1 automation ----
export interface ToolParam { type: "string" | "integer" | "boolean"; description: string; required: boolean; enum: string[] | null }
export interface ToolSpec { name: string; description: string; write: boolean; needs_ai: boolean; params: Record<string, ToolParam> }
export type ApprovalMode = "writes" | "all" | "none";
export const APPROVAL_LABEL: Record<ApprovalMode, string> = {
  writes: "Approve steps that change things",
  all: "Approve every step",
  none: "No approvals (read-only or trusted)",
};
export interface Agent { id: string; name: string; description: string; instructions: string; tools: string[]; approval_mode: ApprovalMode; max_steps: number; enabled: boolean }
export interface WorkflowStep { tool: string; args: Record<string, unknown>; why?: string }
export interface Workflow { id: string; name: string; description: string; steps: WorkflowStep[]; schedule: string; schedule_text: string; approval_mode: ApprovalMode; enabled: boolean; next_run_at: string | null; last_run_at: string | null }
export type RunStatus = "running" | "awaiting_approval" | "completed" | "failed" | "rejected" | "cancelled";
export interface RunSummary { id: string; number: number; source_name: string; kind: string; goal: string; trigger: string; approval_mode: ApprovalMode; status: RunStatus; error: string; started_by: UserBrief | null; created_at: string; finished_at: string | null; step_count: number; waiting_step: number | null }
export interface RunStep { ordinal: number; tool: string; write: boolean; args: Record<string, unknown>; why: string; requires_approval: boolean; status: string; result_summary: string; error: string; decided_by: UserBrief | null; decided_at: string | null; decision_note: string; started_at: string | null; finished_at: string | null }
export interface RunDetail extends RunSummary { steps: RunStep[] }
export const RUN_STATUS: Record<RunStatus, [string, string]> = {
  running: ["Running", "info"], awaiting_approval: ["Needs approval", "warn"], completed: ["Completed", "ok"],
  failed: ["Failed", "crit"], rejected: ["Rejected", "crit"], cancelled: ["Cancelled", "mute"],
};
export const STEP_STATUS: Record<string, [string, string]> = {
  pending: ["Pending", "mute"], awaiting_approval: ["Waiting for approval", "warn"], approved: ["Approved", "info"], running: ["Running", "info"],
  succeeded: ["Done", "ok"], failed: ["Failed", "crit"], rejected: ["Rejected", "crit"], skipped: ["Skipped", "mute"],
};
export interface Integration { id: string; kind: "slack" | "teams" | "webhook"; kind_label: string; name: string; config: Record<string, string>; secret_hint: string; enabled: boolean; last_used_at: string | null; last_ok: boolean | null; last_error: string }
export interface NotificationItem { id: string; kind: string; title: string; body: string; link: string; read: boolean; created_at: string }
