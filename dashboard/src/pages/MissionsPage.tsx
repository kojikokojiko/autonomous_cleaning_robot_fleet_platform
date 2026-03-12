import { useEffect, useState } from "react";
import { MissionTable } from "../components/mission/MissionTable";
import { fetchMissions, assignRobot, createMission } from "../services/api";
import type { Mission } from "../types";
import { Plus } from "lucide-react";

export function MissionsPage() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [showCreate, setShowCreate] = useState(false);

  const loadMissions = () => {
    fetchMissions().then(setMissions).catch(console.error);
  };

  useEffect(() => {
    loadMissions();
    const interval = setInterval(loadMissions, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleAssign = async (missionId: string) => {
    try {
      await assignRobot(missionId);
      loadMissions();
    } catch (err) {
      console.error("Failed to assign robot:", err);
      alert("No eligible robots available");
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold mb-1">Missions</h1>
          <p className="text-gray-400 text-sm">{missions.length} missions</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm transition-colors"
        >
          <Plus size={16} />
          New Mission
        </button>
      </div>

      <MissionTable missions={missions} onAssign={handleAssign} />

      {showCreate && (
        <CreateMissionModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadMissions(); }}
        />
      )}
    </div>
  );
}

const ZONE_OPTIONS = [
  { value: "zone_a",   label: "Zone A" },
  { value: "zone_b",   label: "Zone B" },
  { value: "zone_c",   label: "Zone C" },
  { value: "lobby",    label: "Lobby" },
  { value: "corridor", label: "Corridor" },
];

function CreateMissionModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({
    name: "",
    zone: "zone_a",
    priority: 5,
    scheduled_at: new Date(Date.now() + 3600_000).toISOString().slice(0, 16),
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await createMission({
        ...form,
        facility: "office_building_a",
        scheduled_at: new Date(form.scheduled_at).toISOString(),
      });
      onCreated();
    } catch (err) {
      console.error("Failed to create mission:", err);
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500";

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-bold mb-4">Create Mission</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Mission Name</label>
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Zone A Cleaning"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Zone</label>
              <select
                className={inputClass}
                value={form.zone}
                onChange={(e) => setForm({ ...form, zone: e.target.value })}
              >
                {ZONE_OPTIONS.map(z => (
                  <option key={z.value} value={z.value}>{z.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Priority (1=High)</label>
              <input
                className={inputClass}
                type="number"
                min={1}
                max={10}
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: +e.target.value })}
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Scheduled At</label>
            <input
              className={inputClass}
              type="datetime-local"
              value={form.scheduled_at}
              onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
              required
            />
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">
              Cancel
            </button>
            <button type="submit" disabled={loading} className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm disabled:opacity-50">
              {loading ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
