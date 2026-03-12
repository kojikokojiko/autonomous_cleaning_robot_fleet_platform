import { useEffect, useCallback, useState } from "react";
import { FleetSummaryBar } from "../components/fleet/FleetSummaryBar";
import { RobotCard } from "../components/fleet/RobotCard";
import { EventFeed } from "../components/fleet/EventFeed";
import { FleetMap } from "../components/map/FleetMap";
import { BatteryChart } from "../components/telemetry/BatteryChart";
import { useFleetStore } from "../store/fleetStore";
import { useWebSocket } from "../hooks/useWebSocket";
import { fetchRobots, fetchFleetSummary, fetchTelemetry, registerRobot } from "../services/api";
import type { WebSocketMessage, TelemetryPoint } from "../types";
import { Plus } from "lucide-react";

export function FleetPage() {
  const { robots, summary, events, selectedRobotId, setRobots, updateRobot, setSummary, addEvent, selectRobot } =
    useFleetStore();
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>([]);
  const [showRegister, setShowRegister] = useState(false);

  // Load initial data
  useEffect(() => {
    fetchRobots().then(setRobots).catch(console.error);
    fetchFleetSummary().then(setSummary).catch(console.error);

    // Poll fleet data every 1s (WebSocket handles real-time; poll as fallback)
    const interval = setInterval(() => {
      fetchRobots().then(setRobots).catch(console.error);
      fetchFleetSummary().then(setSummary).catch(console.error);
    }, 1000);
    return () => clearInterval(interval);
  }, [setRobots, setSummary]);

  // Load telemetry for selected robot
  useEffect(() => {
    if (!selectedRobotId) return;
    fetchTelemetry(selectedRobotId, { limit: 60 })
      .then(setTelemetry)
      .catch(console.error);
  }, [selectedRobotId]);

  // WebSocket real-time updates
  const handleWsMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (msg.type === "telemetry_update") {
        const d = msg.data as { robot_id: string; battery_level?: number; position?: { x: number; y: number; floor: number }; status?: string };
        if (d.robot_id) {
          updateRobot(d.robot_id, {
            battery_level: d.battery_level,
            position: d.position,
            status: d.status as never,
            last_seen: new Date().toISOString(),
          });
        }
      } else if (msg.type === "robot_event") {
        addEvent({
          robot_id: (msg.data.robot_id as string) || "unknown",
          event_type: msg.event_type || "Unknown",
          severity: (msg.data.severity as never) || "info",
          occurred_at: new Date().toISOString(),
        });
      }
    },
    [updateRobot, addEvent],
  );

  useWebSocket(handleWsMessage);

  const robotList = Object.values(robots);
  const selectedRobot = selectedRobotId ? robots[selectedRobotId] : null;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold mb-1">Fleet Overview</h1>
          <p className="text-gray-400 text-sm">{robotList.length} robots registered</p>
        </div>
        <button
          onClick={() => setShowRegister(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm transition-colors"
        >
          <Plus size={16} />
          Register Robot
        </button>
      </div>

      {summary && <FleetSummaryBar summary={summary} />}

      <div className="relative">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Live Map</h2>
        <FleetMap robots={robotList} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Robot list */}
        <div className="lg:col-span-2">
          <h2 className="text-sm font-semibold text-gray-400 mb-3">Robots</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {robotList.map((robot) => (
              <RobotCard
                key={robot.robot_id}
                robot={robot}
                selected={robot.robot_id === selectedRobotId}
                onClick={() => selectRobot(robot.robot_id === selectedRobotId ? null : robot.robot_id)}
              />
            ))}
            {robotList.length === 0 && (
              <div className="col-span-2 py-10 text-center text-gray-500 text-sm">
                No robots registered. Start the fleet simulator or register robots via API.
              </div>
            )}
          </div>
        </div>

        {/* Event feed */}
        <div>
          <h2 className="text-sm font-semibold text-gray-400 mb-3">Events</h2>
          <EventFeed events={events} />
        </div>
      </div>

      {/* Telemetry chart for selected robot */}
      {selectedRobot && telemetry.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-400 mb-3">
            Telemetry — {selectedRobot.name}
          </h2>
          <BatteryChart data={telemetry} />
        </div>
      )}

      {showRegister && (
        <RegisterRobotModal
          onClose={() => setShowRegister(false)}
          onRegistered={() => {
            setShowRegister(false);
            fetchRobots().then(setRobots).catch(console.error);
          }}
        />
      )}
    </div>
  );
}

const MODEL_OPTIONS = ["CleanBot Pro", "CleanBot Lite", "SweeperX 3000", "DustMaster 500"];

function RegisterRobotModal({ onClose, onRegistered }: { onClose: () => void; onRegistered: () => void }) {
  const [form, setForm] = useState({ robot_id: "", name: "", model: MODEL_OPTIONS[0] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await registerRobot(form);
      onRegistered();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500";

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-bold mb-4">Register Robot</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Robot ID</label>
            <input
              className={inputClass}
              value={form.robot_id}
              onChange={(e) => setForm({ ...form, robot_id: e.target.value })}
              placeholder="robot_001"
              required
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Name</label>
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Robot 1"
              required
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Model</label>
            <select
              className={inputClass}
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
            >
              {MODEL_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">
              Cancel
            </button>
            <button type="submit" disabled={loading} className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm disabled:opacity-50">
              {loading ? "Registering..." : "Register"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
