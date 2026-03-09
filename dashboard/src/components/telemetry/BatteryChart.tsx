import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { TelemetryPoint } from "../../types";
import { format } from "date-fns";

interface Props {
  data: TelemetryPoint[];
}

export function BatteryChart({ data }: Props) {
  const chartData = data
    .slice()
    .reverse()
    .map((d) => ({
      time: format(new Date(d.time), "HH:mm:ss"),
      battery: d.battery_level ? Math.round(d.battery_level) : null,
      speed: d.speed ? +(d.speed * 100).toFixed(0) : null,
    }));

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">Battery & Speed</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 10, fill: "#9ca3af" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="battery"
            domain={[0, 100]}
            tick={{ fontSize: 10, fill: "#9ca3af" }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: 6 }}
            labelStyle={{ color: "#e5e7eb" }}
            itemStyle={{ color: "#d1d5db" }}
          />
          <ReferenceLine yAxisId="battery" y={20} stroke="#ef4444" strokeDasharray="4 4" />
          <Line
            yAxisId="battery"
            type="monotone"
            dataKey="battery"
            stroke="#22c55e"
            strokeWidth={2}
            dot={false}
            name="Battery %"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
