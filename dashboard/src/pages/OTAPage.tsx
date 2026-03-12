import { useEffect, useState } from "react";
import { Upload, Play, CheckCircle, XCircle, Clock, AlertTriangle } from "lucide-react";
import { clsx } from "clsx";
import { fetchFirmware, createFirmware, fetchOTAJobs, createOTAJobs, fetchRobots } from "../services/api";
import type { Firmware, OTAJob, Robot } from "../types";

const JOB_STATUS_COLOR: Record<string, string> = {
  pending:     "text-gray-400",
  notified:    "text-blue-400",
  downloading: "text-yellow-400",
  applying:    "text-yellow-400",
  completed:   "text-green-400",
  failed:      "text-red-400",
  rolled_back: "text-orange-400",
};

const JOB_STATUS_ICON: Record<string, React.ReactNode> = {
  pending:     <Clock size={13} />,
  notified:    <Clock size={13} />,
  downloading: <Clock size={13} />,
  applying:    <Clock size={13} />,
  completed:   <CheckCircle size={13} />,
  failed:      <XCircle size={13} />,
  rolled_back: <AlertTriangle size={13} />,
};

export function OTAPage() {
  const [firmware, setFirmware] = useState<Firmware[]>([]);
  const [jobs, setJobs] = useState<OTAJob[]>([]);
  const [robots, setRobots] = useState<Robot[]>([]);
  const [showRegisterFw, setShowRegisterFw] = useState(false);
  const [showDeployModal, setShowDeployModal] = useState<Firmware | null>(null);

  const load = () => {
    fetchFirmware().then(setFirmware).catch(console.error);
    fetchOTAJobs().then(setJobs).catch(console.error);
    fetchRobots().then(setRobots).catch(console.error);
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold mb-1">OTA Updates</h1>
          <p className="text-gray-400 text-sm">{firmware.length} firmware versions · {jobs.length} jobs</p>
        </div>
        <button
          onClick={() => setShowRegisterFw(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm transition-colors"
        >
          <Upload size={16} />
          Register Firmware
        </button>
      </div>

      {/* Firmware list */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Firmware Versions</h2>
        {firmware.length === 0 ? (
          <div className="text-center py-10 text-gray-500 text-sm border border-gray-700 rounded-lg">
            No firmware registered yet.
          </div>
        ) : (
          <div className="space-y-2">
            {firmware.map((fw) => (
              <div key={fw.id} className="bg-gray-800 border border-gray-700 rounded-lg p-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-sm">{fw.version}</span>
                      {fw.is_stable && (
                        <span className="text-xs px-1.5 py-0.5 bg-green-900 text-green-300 rounded">stable</span>
                      )}
                      {fw.config?.step_per_cycle != null && (
                        <span className="text-xs px-1.5 py-0.5 bg-blue-900 text-blue-300 rounded font-mono">
                          speed {Number(fw.config.step_per_cycle).toFixed(2)} m/cycle
                        </span>
                      )}
                    </div>
                    {fw.release_notes && (
                      <p className="text-xs text-gray-400 mt-0.5">{fw.release_notes}</p>
                    )}
                    <p className="text-xs text-gray-500 mt-0.5">
                      {fw.file_size_bytes ? `${fw.file_size_bytes} bytes · ` : ""}
                      sha256: {fw.checksum_sha256.slice(0, 16)}… · {new Date(fw.uploaded_at).toLocaleString()}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setShowDeployModal(fw)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-green-700 hover:bg-green-600 rounded-lg text-xs transition-colors"
                >
                  <Play size={13} />
                  Deploy
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* OTA Jobs */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Job History</h2>
        {jobs.length === 0 ? (
          <div className="text-center py-10 text-gray-500 text-sm border border-gray-700 rounded-lg">
            No OTA jobs yet.
          </div>
        ) : (
          <div className="overflow-hidden border border-gray-700 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-gray-700/50 text-gray-400 text-xs">
                <tr>
                  <th className="text-left px-4 py-2">Robot</th>
                  <th className="text-left px-4 py-2">Firmware</th>
                  <th className="text-left px-4 py-2">Strategy</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2">Attempts</th>
                  <th className="text-left px-4 py-2">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {jobs.map((job) => {
                  const robot = robots.find((r) => r.id === job.robot_id);
                  const fw = firmware.find((f) => f.id === job.firmware_id);
                  return (
                    <tr key={job.id} className="hover:bg-gray-700/30">
                      <td className="px-4 py-3 font-mono text-xs">
                        {robot?.robot_id ?? job.robot_id.slice(0, 8) + "…"}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-blue-300">
                        {fw?.version ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className={clsx(
                          "text-xs px-2 py-0.5 rounded",
                          job.strategy === "canary" ? "bg-purple-900 text-purple-300" : "bg-gray-700 text-gray-300"
                        )}>
                          {job.strategy}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={clsx("flex items-center gap-1 text-xs", JOB_STATUS_COLOR[job.status] ?? "text-gray-400")}>
                          {JOB_STATUS_ICON[job.status] ?? <Clock size={13} />}
                          {job.status}
                        </span>
                        {job.error_message && (
                          <p className="text-xs text-red-400 mt-0.5">{job.error_message}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-400">{job.attempts}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showRegisterFw && (
        <RegisterFirmwareModal
          onClose={() => setShowRegisterFw(false)}
          onRegistered={() => { setShowRegisterFw(false); load(); }}
        />
      )}

      {showDeployModal && (
        <DeployModal
          firmware={showDeployModal}
          robots={robots}
          onClose={() => setShowDeployModal(null)}
          onDeployed={() => { setShowDeployModal(null); load(); }}
        />
      )}
    </div>
  );
}

// ---- Register Firmware Modal ----

function RegisterFirmwareModal({ onClose, onRegistered }: { onClose: () => void; onRegistered: () => void }) {
  const [form, setForm] = useState({
    version: "", release_notes: "", is_stable: false,
    step_per_cycle: 0.5, s3_key: "", checksum_sha256: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await createFirmware({
        version: form.version,
        s3_key: form.s3_key,
        checksum_sha256: form.checksum_sha256,
        release_notes: form.release_notes || undefined,
        is_stable: form.is_stable,
        config: { step_per_cycle: form.step_per_cycle },
      });
      onRegistered();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500";

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-bold mb-4">Register Firmware</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Version</label>
              <input className={inputClass} value={form.version}
                onChange={(e) => setForm({ ...form, version: e.target.value })}
                placeholder="v1.2.3" required />
            </div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.is_stable}
                  onChange={(e) => setForm({ ...form, is_stable: e.target.checked })}
                  className="w-4 h-4 accent-blue-500" />
                <span className="text-gray-300">Stable</span>
              </label>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Release Notes</label>
            <textarea className={inputClass} rows={2} value={form.release_notes}
              onChange={(e) => setForm({ ...form, release_notes: e.target.value })}
              placeholder="Bug fixes and performance improvements" />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">
              Robot Speed (step_per_cycle)
              <span className="ml-2 text-blue-400 font-mono">{form.step_per_cycle.toFixed(2)} m/cycle</span>
            </label>
            <input
              type="range" min="0.1" max="2.0" step="0.05"
              value={form.step_per_cycle}
              onChange={(e) => setForm({ ...form, step_per_cycle: parseFloat(e.target.value) })}
              className="w-full accent-blue-500"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-0.5">
              <span>0.1 (slow)</span>
              <span className="text-gray-400">default: 0.50</span>
              <span>2.0 (fast)</span>
            </div>
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
            <button type="submit" disabled={loading} className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm disabled:opacity-50">
              {loading ? "Registering..." : "Register"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---- Deploy Modal ----

function DeployModal({
  firmware, robots, onClose, onDeployed,
}: {
  firmware: Firmware;
  robots: Robot[];
  onClose: () => void;
  onDeployed: () => void;
}) {
  const eligibleRobots = robots.filter(
    (r) => (r.status === "idle" || r.status === "docked") && r.firmware_version !== firmware.version,
  );
  const alreadyUpToDate = robots.filter((r) => r.firmware_version === firmware.version);
  const [selectedIds, setSelectedIds] = useState<string[]>(eligibleRobots.map((r) => r.robot_id));
  const [strategy, setStrategy] = useState<"rolling" | "canary">("rolling");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const toggle = (id: string) =>
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const handleDeploy = async () => {
    if (selectedIds.length === 0) { setError("Select at least one robot"); return; }
    setLoading(true);
    setError("");
    try {
      await createOTAJobs({ firmware_id: firmware.id, robot_ids: selectedIds, strategy });
      onDeployed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-bold mb-1">Deploy Firmware</h2>
        <p className="text-sm text-blue-300 font-mono mb-4">{firmware.version}</p>

        {/* Strategy */}
        <div className="mb-4">
          <label className="text-xs text-gray-400 mb-2 block">Strategy</label>
          <div className="flex gap-3">
            {(["rolling", "canary"] as const).map((s) => (
              <button key={s} onClick={() => setStrategy(s)}
                className={clsx(
                  "flex-1 py-2 rounded-lg text-sm border transition-colors",
                  strategy === s
                    ? "border-blue-500 bg-blue-900/40 text-blue-300"
                    : "border-gray-600 text-gray-400 hover:border-gray-500"
                )}>
                {s === "rolling" ? "🔄 Rolling" : "🐤 Canary"}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-1.5">
            {strategy === "rolling"
              ? "全ロボットを順番に更新。1台失敗したら停止。"
              : "まず1台だけ更新。問題なければ残りに展開。"}
          </p>
        </div>

        {/* Robot selection */}
        <div className="mb-4">
          <label className="text-xs text-gray-400 mb-2 block">
            Target Robots — idle / docked のみ対象 ({eligibleRobots.length}台)
          </label>
          {eligibleRobots.length === 0 && alreadyUpToDate.length === 0 ? (
            <p className="text-xs text-yellow-400 py-2">対象ロボットがいません (idle / docked が必要)</p>
          ) : (
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {eligibleRobots.map((r) => (
                <label key={r.robot_id} className="flex items-center gap-2 text-sm cursor-pointer px-2 py-1.5 rounded hover:bg-gray-700">
                  <input type="checkbox" checked={selectedIds.includes(r.robot_id)}
                    onChange={() => toggle(r.robot_id)}
                    className="w-4 h-4 accent-blue-500" />
                  <span className="font-mono">{r.robot_id}</span>
                  <span className="text-xs text-gray-500">{r.name}</span>
                  <span className="ml-auto text-xs text-blue-400">{r.status}</span>
                </label>
              ))}
              {alreadyUpToDate.map((r) => (
                <div key={r.robot_id} className="flex items-center gap-2 text-sm px-2 py-1.5 rounded opacity-40 cursor-not-allowed">
                  <input type="checkbox" disabled checked={false} className="w-4 h-4" />
                  <span className="font-mono text-gray-500">{r.robot_id}</span>
                  <span className="text-xs text-gray-600">{r.name}</span>
                  <span className="ml-auto text-xs text-green-600 flex items-center gap-1">
                    <CheckCircle size={11} /> already {firmware.version}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {error && <p className="text-red-400 text-xs mb-3">{error}</p>}

        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
          <button onClick={handleDeploy} disabled={loading || selectedIds.length === 0}
            className="flex-1 py-2 bg-green-700 hover:bg-green-600 rounded-lg text-sm disabled:opacity-50 flex items-center justify-center gap-2">
            <Play size={14} />
            {loading ? "Deploying..." : `Deploy to ${selectedIds.length} robots`}
          </button>
        </div>
      </div>
    </div>
  );
}
