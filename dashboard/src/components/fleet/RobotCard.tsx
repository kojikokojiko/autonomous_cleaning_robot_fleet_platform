import { useState } from "react";
import { Battery, MapPin, Clock, Wifi, WifiOff, Check, Loader, Layers } from "lucide-react";
import { clsx } from "clsx";
import type { Robot } from "../../types";
import { sendCommand } from "../../services/api";

const ZONE_OPTIONS = [
  { id: "zone_a",   label: "Zone A" },
  { id: "zone_b",   label: "Zone B" },
  { id: "zone_c",   label: "Zone C" },
  { id: "lobby",    label: "Lobby" },
  { id: "corridor", label: "Corridor" },
];

const ZONE_DEFS = [
  { id: "lobby",    label: "Lobby",    x_min: 1.0, x_max: 5.0,  z_min: 1.0,  z_max: 7.8  },
  { id: "zone_a",   label: "Zone A",   x_min: 7.0, x_max: 24.0, z_min: 1.0,  z_max: 7.8  },
  { id: "corridor", label: "Corridor", x_min: 1.0, x_max: 24.0, z_min: 9.7,  z_max: 10.3 },
  { id: "zone_b",   label: "Zone B",   x_min: 1.0, x_max: 12.0, z_min: 12.0, z_max: 18.8 },
  { id: "zone_c",   label: "Zone C",   x_min: 14.0, x_max: 24.0, z_min: 12.0, z_max: 18.8 },
];

function currentZoneLabel(x: number, z: number): string {
  const found = ZONE_DEFS.find(d => x >= d.x_min && x <= d.x_max && z >= d.z_min && z <= d.z_max);
  return found?.label ?? "—";
}

const STATUS_COLORS: Record<string, string> = {
  offline:    "bg-gray-600 text-gray-200",
  idle:       "bg-blue-600 text-blue-100",
  cleaning:   "bg-green-600 text-green-100",
  charging:   "bg-yellow-600 text-yellow-100",
  docked:     "bg-yellow-700 text-yellow-100",
  error:      "bg-red-600 text-red-100",
  ota_update: "bg-purple-600 text-purple-100",
};

const BATTERY_COLOR = (pct?: number | null) => {
  if (pct == null) return "text-gray-400";
  if (pct < 20) return "text-red-400";
  if (pct < 50) return "text-yellow-400";
  return "text-green-400";
};

interface RobotCardProps {
  robot: Robot;
  selected?: boolean;
  onClick?: () => void;
}

type CmdState = "idle" | "sending" | "sent" | "error";

export function RobotCard({ robot, selected, onClick }: RobotCardProps) {
  const isOnline = robot.status !== "offline";
  const [dockState, setDockState]   = useState<CmdState>("idle");
  const [stopState, setStopState]   = useState<CmdState>("idle");
  const [startState, setStartState] = useState<CmdState>("idle");
  const [selectedZone, setSelectedZone] = useState("zone_a");

  const runCmd = async (
    type: string,
    setState: (s: CmdState) => void,
    payload?: Record<string, unknown>,
  ) => {
    setState("sending");
    try {
      await sendCommand(robot.robot_id, type, payload);
      setState("sent");
      setTimeout(() => setState("idle"), 2500);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 3000);
    }
  };

  const handleStartMission = (e: React.MouseEvent) => {
    e.stopPropagation();
    runCmd("start_mission", setStartState, {
      mission_id: `manual_${Date.now()}`,
      zone: selectedZone,
    });
  };

  const handleReturnToDock = (e: React.MouseEvent) => {
    e.stopPropagation();
    runCmd("return_to_dock", setDockState);
  };

  const handleEmergencyStop = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Emergency stop ${robot.name}?`)) return;
    runCmd("emergency_stop", setStopState);
  };

  const CmdBtn = ({
    label, state, onClick: handleClick, danger,
  }: { label: string; state: CmdState; onClick: (e: React.MouseEvent) => void; danger?: boolean }) => (
    <button
      onClick={handleClick}
      disabled={state === "sending"}
      className={clsx(
        "flex-1 flex items-center justify-center gap-1 text-xs py-1 rounded transition-colors disabled:opacity-60",
        danger
          ? "bg-red-900 hover:bg-red-800 text-red-200"
          : state === "sent"
            ? "bg-green-800 text-green-200"
            : state === "error"
              ? "bg-red-800 text-red-200"
              : "bg-gray-700 hover:bg-gray-600",
      )}
    >
      {state === "sending" && <Loader size={11} className="animate-spin" />}
      {state === "sent"    && <Check size={11} />}
      {state === "idle" || state === "error" ? label : state === "sending" ? "…" : "Sent"}
    </button>
  );

  return (
    <div
      onClick={onClick}
      className={clsx(
        "rounded-lg border p-4 cursor-pointer transition-all",
        "bg-gray-800 hover:bg-gray-750",
        selected ? "border-blue-500 ring-1 ring-blue-500" : "border-gray-700",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {isOnline
            ? <Wifi size={14} className="text-green-400" />
            : <WifiOff size={14} className="text-gray-500" />
          }
          <span className="font-semibold text-sm">{robot.name}</span>
          {robot.firmware_version && (
            <span className="text-xs px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded font-mono">
              {robot.firmware_version}
            </span>
          )}
        </div>
        <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", STATUS_COLORS[robot.status])}>
          {robot.status.replace("_", " ")}
        </span>
      </div>

      {/* Battery */}
      <div className="flex items-center gap-1 mb-2">
        <Battery size={14} className={BATTERY_COLOR(robot.battery_level)} />
        <span className={clsx("text-sm font-mono", BATTERY_COLOR(robot.battery_level))}>
          {robot.battery_level != null ? `${robot.battery_level.toFixed(0)}%` : "—"}
        </span>
        {robot.battery_level != null && (
          <div className="flex-1 h-1.5 bg-gray-700 rounded-full ml-2">
            <div
              className={clsx("h-full rounded-full transition-all", {
                "bg-red-500":    robot.battery_level < 20,
                "bg-yellow-500": robot.battery_level >= 20 && robot.battery_level < 50,
                "bg-green-500":  robot.battery_level >= 50,
              })}
              style={{ width: `${robot.battery_level}%` }}
            />
          </div>
        )}
      </div>

      {/* Position */}
      {robot.position && (
        <div className="flex items-center gap-1 text-xs text-gray-400 mb-3">
          <MapPin size={12} />
          <span>({robot.position.x.toFixed(1)}, {robot.position.y.toFixed(1)}) F{robot.position.floor}</span>
        </div>
      )}

      {/* Current zone (when cleaning) */}
      {robot.status === "cleaning" && robot.position && (
        <div className="flex items-center gap-1 text-xs text-green-400 mb-1">
          <Layers size={11} />
          <span>Cleaning: <span className="font-semibold">{currentZoneLabel(robot.position.x, robot.position.y)}</span></span>
        </div>
      )}

      {/* Actions */}
      {isOnline && (
        <div className="mt-3 pt-3 border-t border-gray-700 space-y-2">
          {/* Zone selector */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-400 whitespace-nowrap">Zone:</label>
            <select
              value={selectedZone}
              onChange={e => { e.stopPropagation(); setSelectedZone(e.target.value); }}
              onClick={e => e.stopPropagation()}
              className="flex-1 text-xs bg-gray-700 border border-gray-600 rounded px-2 py-1 text-gray-200 focus:outline-none focus:border-blue-500"
            >
              {ZONE_OPTIONS.map(z => (
                <option key={z.id} value={z.id}>{z.label}</option>
              ))}
            </select>
            <CmdBtn label="▶ Start" state={startState} onClick={handleStartMission} />
          </div>
          <div className="flex gap-2">
            <CmdBtn label="Return to Dock"  state={dockState}  onClick={handleReturnToDock} />
            <CmdBtn label="Emergency Stop"  state={stopState}  onClick={handleEmergencyStop} danger />
          </div>
        </div>
      )}

      {/* Last seen */}
      {robot.last_seen && (
        <div className="flex items-center gap-1 text-xs text-gray-500 mt-2">
          <Clock size={10} />
          <span>{new Date(robot.last_seen).toLocaleTimeString()}</span>
        </div>
      )}
    </div>
  );
}
