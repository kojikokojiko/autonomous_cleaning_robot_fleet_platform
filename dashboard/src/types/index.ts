export type RobotStatus =
  | "offline"
  | "idle"
  | "cleaning"
  | "charging"
  | "docked"
  | "error"
  | "ota_update";

export type MissionStatus =
  | "pending"
  | "assigned"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled";

export interface Position {
  x: number;
  y: number;
  floor: number;
}

export interface Robot {
  id: string;
  robot_id: string;
  name: string;
  facility?: string;
  model?: string;
  firmware_version?: string;
  status: RobotStatus;
  battery_level?: number;
  position?: Position;
  last_seen?: string;
  registered_at: string;
  updated_at: string;
}

export interface FleetSummary {
  total: number;
  online: number;
  cleaning: number;
  idle: number;
  charging: number;
  error: number;
  avg_battery?: number;
}

export interface Mission {
  id: string;
  name: string;
  facility?: string;
  zone: string;
  priority: number;
  status: MissionStatus;
  assigned_robot?: string;
  scheduled_at: string;
  started_at?: string;
  completed_at?: string;
  coverage_pct: number;
  created_by?: string;
  created_at: string;
}

export interface TelemetryPoint {
  time: string;
  robot_id: string;
  battery_level?: number;
  position_x?: number;
  position_y?: number;
  position_floor?: number;
  nav_status?: string;
  motor_load_left?: number;
  motor_load_right?: number;
  mission_progress?: number;
  speed?: number;
}

export interface RobotEvent {
  id?: string;
  robot_id: string;
  event_type: string;
  severity: "info" | "warning" | "error" | "critical";
  payload?: Record<string, unknown>;
  occurred_at?: string;
}

export interface Firmware {
  id: string;
  version: string;
  s3_key: string;
  checksum_sha256: string;
  file_size_bytes?: number;
  release_notes?: string;
  is_stable: boolean;
  config?: Record<string, unknown>;
  uploaded_by?: string;
  uploaded_at: string;
}

export interface OTAJob {
  id: string;
  firmware_id: string;
  robot_id: string;
  strategy: "rolling" | "canary";
  status: string;
  attempts: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface WebSocketMessage {
  type: "telemetry_update" | "robot_event" | "mission_update";
  event_type?: string;
  data: Record<string, unknown>;
}
