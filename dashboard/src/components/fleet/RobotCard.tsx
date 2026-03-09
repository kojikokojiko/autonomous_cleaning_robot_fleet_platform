import { Battery, MapPin, Clock, Wifi, WifiOff } from "lucide-react";
import { clsx } from "clsx";
import type { Robot } from "../../types";
import { sendCommand } from "../../services/api";

const STATUS_COLORS: Record<string, string> = {
  offline:    "bg-gray-600 text-gray-200",
  idle:       "bg-blue-600 text-blue-100",
  cleaning:   "bg-green-600 text-green-100",
  charging:   "bg-yellow-600 text-yellow-100",
  docked:     "bg-yellow-700 text-yellow-100",
  error:      "bg-red-600 text-red-100",
  ota_update: "bg-purple-600 text-purple-100",
};

const BATTERY_COLOR = (pct?: number) => {
  if (pct === undefined) return "text-gray-400";
  if (pct < 20) return "text-red-400";
  if (pct < 50) return "text-yellow-400";
  return "text-green-400";
};

interface RobotCardProps {
  robot: Robot;
  selected?: boolean;
  onClick?: () => void;
}

export function RobotCard({ robot, selected, onClick }: RobotCardProps) {
  const isOnline = robot.status !== "offline";

  const handleEmergencyStop = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Emergency stop ${robot.name}?`)) return;
    try {
      await sendCommand(robot.robot_id, "emergency_stop");
    } catch (err) {
      console.error("Failed to send emergency stop:", err);
    }
  };

  const handleReturnToDock = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await sendCommand(robot.robot_id, "return_to_dock");
  };

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
        </div>
        <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", STATUS_COLORS[robot.status])}>
          {robot.status.replace("_", " ")}
        </span>
      </div>

      {/* Battery */}
      <div className="flex items-center gap-1 mb-2">
        <Battery size={14} className={BATTERY_COLOR(robot.battery_level)} />
        <span className={clsx("text-sm font-mono", BATTERY_COLOR(robot.battery_level))}>
          {robot.battery_level !== undefined ? `${robot.battery_level.toFixed(0)}%` : "—"}
        </span>
        {robot.battery_level !== undefined && (
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

      {/* Actions */}
      {isOnline && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-gray-700">
          <button
            onClick={handleReturnToDock}
            className="flex-1 text-xs py-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
          >
            Return to Dock
          </button>
          <button
            onClick={handleEmergencyStop}
            className="flex-1 text-xs py-1 bg-red-900 hover:bg-red-800 text-red-200 rounded transition-colors"
          >
            Emergency Stop
          </button>
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
