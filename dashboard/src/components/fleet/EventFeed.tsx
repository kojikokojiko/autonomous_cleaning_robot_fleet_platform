import { AlertTriangle, Info, AlertCircle, Zap } from "lucide-react";
import { clsx } from "clsx";
import type { RobotEvent } from "../../types";

const SEVERITY_CONFIG = {
  info:     { icon: <Info size={14} />,          color: "text-blue-400",   bg: "bg-blue-950/40" },
  warning:  { icon: <AlertTriangle size={14} />, color: "text-yellow-400", bg: "bg-yellow-950/40" },
  error:    { icon: <AlertCircle size={14} />,   color: "text-red-400",    bg: "bg-red-950/40" },
  critical: { icon: <Zap size={14} />,           color: "text-red-300",    bg: "bg-red-950/60" },
};

interface Props {
  events: RobotEvent[];
}

export function EventFeed({ events }: Props) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 h-80 overflow-y-auto">
      <h3 className="text-sm font-semibold text-gray-300 mb-3 sticky top-0 bg-gray-800 pb-2">
        Event Feed
      </h3>
      {events.length === 0 ? (
        <p className="text-gray-500 text-sm">No events yet</p>
      ) : (
        <div className="space-y-2">
          {events.map((event, i) => {
            const cfg = SEVERITY_CONFIG[event.severity] || SEVERITY_CONFIG.info;
            return (
              <div
                key={i}
                className={clsx("flex items-start gap-2 rounded p-2 text-xs", cfg.bg)}
              >
                <span className={clsx("mt-0.5 shrink-0", cfg.color)}>{cfg.icon}</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={clsx("font-semibold", cfg.color)}>
                      {event.event_type}
                    </span>
                    <span className="text-gray-500 text-[10px]">{event.robot_id}</span>
                  </div>
                  {event.occurred_at && (
                    <div className="text-gray-500 text-[10px] mt-0.5">
                      {new Date(event.occurred_at).toLocaleTimeString()}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
