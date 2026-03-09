import { useEffect, useCallback } from "react";
import { FleetSummaryBar } from "../components/fleet/FleetSummaryBar";
import { RobotCard } from "../components/fleet/RobotCard";
import { EventFeed } from "../components/fleet/EventFeed";
import { FleetMap } from "../components/map/FleetMap";
import { BatteryChart } from "../components/telemetry/BatteryChart";
import { useFleetStore } from "../store/fleetStore";
import { useWebSocket } from "../hooks/useWebSocket";
import { fetchRobots, fetchFleetSummary, fetchTelemetry } from "../services/api";
import type { WebSocketMessage, TelemetryPoint } from "../types";
import { useState } from "react";

export function FleetPage() {
  const { robots, summary, events, selectedRobotId, setRobots, updateRobot, setSummary, addEvent, selectRobot } =
    useFleetStore();
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>([]);

  // Load initial data
  useEffect(() => {
    fetchRobots().then(setRobots).catch(console.error);
    fetchFleetSummary().then(setSummary).catch(console.error);

    // Poll fleet data every 5s
    const interval = setInterval(() => {
      fetchRobots().then(setRobots).catch(console.error);
      fetchFleetSummary().then(setSummary).catch(console.error);
    }, 5000);
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
      <div>
        <h1 className="text-xl font-bold mb-1">Fleet Overview</h1>
        <p className="text-gray-400 text-sm">{robotList.length} robots registered</p>
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
    </div>
  );
}
