import type { Robot, FleetSummary, Mission, MissionStatus, TelemetryPoint, Firmware, OTAJob } from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ---- Fleet Service ----
export const registerRobot = (data: { robot_id: string; name: string; model?: string }) =>
  request<Robot>("/api/v1/robots", { method: "POST", body: JSON.stringify({ ...data, facility: "office_building_a" }) });

export const fetchRobots = (params?: { facility?: string; status?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return request<Robot[]>(`/api/v1/robots${qs ? `?${qs}` : ""}`);
};

export const fetchRobot = (robotId: string) =>
  request<Robot>(`/api/v1/robots/${robotId}`);

export const fetchFleetSummary = (facility?: string) => {
  const qs = facility ? `?facility=${facility}` : "";
  return request<FleetSummary>(`/api/v1/robots/summary${qs}`);
};

// ---- Mission Service ----
export const fetchMissions = (params?: { status?: MissionStatus; facility?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return request<Mission[]>(`/api/v1/missions${qs ? `?${qs}` : ""}`);
};

export const createMission = (data: {
  name: string;
  facility: string;
  zone: string;
  priority?: number;
  scheduled_at: string;
}) => request<Mission>("/api/v1/missions", { method: "POST", body: JSON.stringify(data) });

export const assignRobot = (missionId: string) =>
  request<Mission>(`/api/v1/missions/${missionId}/assign`, { method: "POST" });

// ---- Command Service ----
export const sendCommand = (robotId: string, commandType: string, payload?: Record<string, unknown>) =>
  request(`/api/v1/commands`, {
    method: "POST",
    body: JSON.stringify({ robot_id: robotId, command_type: commandType, payload }),
  });

// ---- OTA Service ----
export const fetchFirmware = () =>
  request<Firmware[]>("/api/v1/ota/firmware");

export const createFirmware = (data: {
  version: string; s3_key: string; checksum_sha256: string;
  file_size_bytes?: number; release_notes?: string; is_stable?: boolean;
  config?: Record<string, unknown>;
}) => request<Firmware>("/api/v1/ota/firmware", { method: "POST", body: JSON.stringify(data) });

export const fetchOTAJobs = (robotId?: string) => {
  const qs = robotId ? `?robot_id=${robotId}` : "";
  return request<OTAJob[]>(`/api/v1/ota/jobs${qs}`);
};

export const createOTAJobs = (data: {
  firmware_id: string; robot_ids: string[]; strategy: "rolling" | "canary";
}) => request<OTAJob[]>("/api/v1/ota/jobs", { method: "POST", body: JSON.stringify(data) });

// ---- Telemetry Service ----
export const fetchTelemetry = (robotId: string, params?: { from_ts?: string; to_ts?: string; limit?: number }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return request<TelemetryPoint[]>(`/api/v1/telemetry/${robotId}${qs ? `?${qs}` : ""}`);
};

export const fetchLatestTelemetry = (robotId: string) =>
  request<TelemetryPoint>(`/api/v1/telemetry/${robotId}/latest`);
