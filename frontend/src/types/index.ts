// Frontend TypeScript types — mirror the FastAPI Pydantic response schemas exactly.

export type VmStatus = "running" | "stopped" | "archived";

export interface Snapshot {
  id: number;
  description: string;
  created_at: string;
  vm_name: string;
  server_type?: string | null;
  location?: string | null;
}

export interface VirtualMachine {
  name: string;
  status: VmStatus;
  server_id?: number;
  public_ip?: string;
  server_type?: string | null;
  location?: string | null;
  domain?: string | null;
  protected?: boolean;
  latest_snapshot?: Snapshot;
  can_restore: boolean;
  can_archive: boolean;
  can_start: boolean;
  can_stop: boolean;
  can_delete_image?: boolean;
}

export type OperationStepStatus = "pending" | "in-progress" | "done" | "error";

export interface OperationStep {
  step: string;
  status: OperationStepStatus;
  message?: string;
}

export type OperationEventKind = "step" | "complete" | "error" | "warning";

export interface OperationEvent {
  kind: OperationEventKind;
  step?: OperationStep;
  summary?: string;
  message?: string;
  completedSteps?: string[];
}

export interface FirewallSyncResult {
  ip: string;
  alreadyPresent: boolean;
}

export interface IpDetectionResult {
  ip: string;
}

export interface VmConfig {
  id: number;
  vm_name: string;
  domain: string | null;
  preferred_server_type: string | null;
}

export interface VmFirewallTarget {
  id: number;
  vm_name: string;
  project_id: number;
  project_name: string;
  firewall_name: string;
}

export const HETZNER_SERVER_TYPES = [
  "cx23", "cx33", "cx43", "cx53",
  "cax11", "cax21", "cax31", "cax41",
  "cpx11", "cpx21", "cpx31", "cpx41", "cpx51",
  "ccx13", "ccx23", "ccx33", "ccx43", "ccx53", "ccx63",
] as const;

export interface HetznerProject {
  id: number;
  name: string;
  firewall_name: string;
  firewall_internal: string;
  cloudflare_zone_id: string;
  cloudflare_api_token: string;
  is_active: boolean;
}

export interface User {
  id: number;
  username: string;
  name: string | null;
  email: string | null;
  is_superadmin: boolean;
  is_active: boolean;
}

export type OperationStatus = "in-progress" | "done" | "error";

export interface OperationLog {
  id: number;
  vm_name: string;
  operation: string;
  status: OperationStatus;
  initiated_by: string;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}
