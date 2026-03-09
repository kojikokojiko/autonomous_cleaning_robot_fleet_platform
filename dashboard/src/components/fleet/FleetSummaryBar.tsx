import { Activity, Bot, Zap, AlertTriangle } from "lucide-react";
import type { FleetSummary } from "../../types";

interface Props {
  summary: FleetSummary;
}

export function FleetSummaryBar({ summary }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <StatCard icon={<Bot size={20} />} label="Total Robots" value={summary.total} color="text-blue-400" />
      <StatCard icon={<Activity size={20} />} label="Online" value={summary.online} color="text-green-400" />
      <StatCard icon={<Bot size={20} />} label="Cleaning" value={summary.cleaning} color="text-emerald-400" />
      <StatCard icon={<Zap size={20} />} label="Charging" value={summary.charging} color="text-yellow-400" />
      <StatCard icon={<AlertTriangle size={20} />} label="Errors" value={summary.error} color="text-red-400" />
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <div className={`flex items-center gap-2 mb-1 ${color}`}>
        {icon}
        <span className="text-xs text-gray-400">{label}</span>
      </div>
      <div className={`text-3xl font-bold ${color}`}>{value}</div>
    </div>
  );
}
