import { clsx } from "clsx";
import type { Mission, MissionStatus } from "../../types";

const STATUS_STYLES: Record<MissionStatus, string> = {
  pending:     "bg-gray-700 text-gray-300",
  assigned:    "bg-blue-900 text-blue-200",
  in_progress: "bg-green-900 text-green-200",
  completed:   "bg-gray-800 text-gray-400",
  failed:      "bg-red-900 text-red-200",
  cancelled:   "bg-gray-800 text-gray-500",
};

const PRIORITY_COLOR = (p: number) => {
  if (p <= 2) return "text-red-400";
  if (p <= 5) return "text-yellow-400";
  return "text-gray-400";
};

interface Props {
  missions: Mission[];
  onAssign?: (missionId: string) => void;
}

export function MissionTable({ missions, onAssign }: Props) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
      <div className="p-4 border-b border-gray-700">
        <h3 className="text-sm font-semibold text-gray-300">Missions</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 border-b border-gray-700">
              <th className="text-left py-2 px-4">Name</th>
              <th className="text-left py-2 px-4">Zone</th>
              <th className="text-left py-2 px-4">Priority</th>
              <th className="text-left py-2 px-4">Status</th>
              <th className="text-left py-2 px-4">Coverage</th>
              <th className="text-left py-2 px-4">Scheduled</th>
              <th className="py-2 px-4"></th>
            </tr>
          </thead>
          <tbody>
            {missions.map((mission) => (
              <tr key={mission.id} className="border-b border-gray-700/50 hover:bg-gray-750">
                <td className="py-2 px-4 font-medium">{mission.name}</td>
                <td className="py-2 px-4 text-gray-400">{mission.zone}</td>
                <td className={clsx("py-2 px-4 font-mono font-bold", PRIORITY_COLOR(mission.priority))}>
                  P{mission.priority}
                </td>
                <td className="py-2 px-4">
                  <span className={clsx("text-xs px-2 py-0.5 rounded-full", STATUS_STYLES[mission.status])}>
                    {mission.status.replace("_", " ")}
                  </span>
                </td>
                <td className="py-2 px-4">
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-gray-700 rounded-full">
                      <div
                        className="h-full bg-green-500 rounded-full"
                        style={{ width: `${mission.coverage_pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-400">{mission.coverage_pct.toFixed(0)}%</span>
                  </div>
                </td>
                <td className="py-2 px-4 text-xs text-gray-400">
                  {new Date(mission.scheduled_at).toLocaleString()}
                </td>
                <td className="py-2 px-4">
                  {mission.status === "pending" && onAssign && (
                    <button
                      onClick={() => onAssign(mission.id)}
                      className="text-xs px-3 py-1 bg-blue-700 hover:bg-blue-600 rounded transition-colors"
                    >
                      Assign
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {missions.length === 0 && (
          <div className="py-8 text-center text-gray-500 text-sm">No missions found</div>
        )}
      </div>
    </div>
  );
}
