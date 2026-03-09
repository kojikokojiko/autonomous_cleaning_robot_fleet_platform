import { create } from "zustand";
import type { Robot, FleetSummary, RobotEvent } from "../types";

interface FleetState {
  robots: Record<string, Robot>;
  summary: FleetSummary | null;
  events: RobotEvent[];
  selectedRobotId: string | null;

  setRobots: (robots: Robot[]) => void;
  updateRobot: (robotId: string, patch: Partial<Robot>) => void;
  setSummary: (summary: FleetSummary) => void;
  addEvent: (event: RobotEvent) => void;
  selectRobot: (robotId: string | null) => void;
}

export const useFleetStore = create<FleetState>((set) => ({
  robots: {},
  summary: null,
  events: [],
  selectedRobotId: null,

  setRobots: (robots) =>
    set({
      robots: Object.fromEntries(robots.map((r) => [r.robot_id, r])),
    }),

  updateRobot: (robotId, patch) =>
    set((state) => ({
      robots: {
        ...state.robots,
        [robotId]: state.robots[robotId]
          ? { ...state.robots[robotId], ...patch }
          : state.robots[robotId],
      },
    })),

  setSummary: (summary) => set({ summary }),

  addEvent: (event) =>
    set((state) => ({
      events: [event, ...state.events].slice(0, 200), // keep last 200 events
    })),

  selectRobot: (robotId) => set({ selectedRobotId: robotId }),
}));
