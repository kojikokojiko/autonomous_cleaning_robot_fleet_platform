import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Text, Line } from "@react-three/drei";
import * as THREE from "three";
import type { Robot } from "../../types";

// ── colour palette ──────────────────────────────────────────────────────────
const STATUS_COLOR: Record<string, string> = {
  offline:    "#4b5563",
  idle:       "#3b82f6",
  cleaning:   "#22c55e",
  charging:   "#f59e0b",
  docked:     "#d97706",
  error:      "#ef4444",
  ota_update: "#a855f7",
};

// ── floor plan ───────────────────────────────────────────────────────────────
// coordinate system: x = east, z = south  (Y is up)
const ZONES = [
  { id: "lobby",     label: "Lobby",           x: 0,  z: 0,  w: 6,  d: 9,  color: "#334155" },
  { id: "zone_a",    label: "Office Zone A",    x: 6,  z: 0,  w: 19, d: 9,  color: "#1e3a5f" },
  { id: "corridor",  label: "Corridor",         x: 0,  z: 9,  w: 25, d: 2,  color: "#3f3f46" },
  { id: "zone_b",    label: "Office Zone B",    x: 0,  z: 11, w: 13, d: 9,  color: "#1e3a5f" },
  { id: "zone_c",    label: "Office Zone C",    x: 13, z: 11, w: 12, d: 9,  color: "#14532d" },
  { id: "charging",  label: "Charging Bay",     x: 0,  z: 16, w: 4,  d: 4,  color: "#78350f" },
];

// thin walls between zones (x, z, length, axis)
const WALLS: { x: number; z: number; len: number; axis: "x" | "z" }[] = [
  // ── outer perimeter ──────────────────────────────────────────────────────
  { x: 12.5, z: 0,  len: 25, axis: "x" }, // north wall
  { x: 12.5, z: 20, len: 25, axis: "x" }, // south wall
  { x: 0,    z: 10, len: 20, axis: "z" }, // west wall
  { x: 25,   z: 10, len: 20, axis: "z" }, // east wall
  // ── interior dividers ────────────────────────────────────────────────────
  { x: 6,  z: 4.5, len: 9,  axis: "z" }, // lobby | zone_a
  { x: 0,  z: 11,  len: 4,  axis: "x" }, // charging wall top
  { x: 4,  z: 18,  len: 5,  axis: "z" }, // charging bay wall
  { x: 13, z: 15,  len: 9,  axis: "z" }, // zone_b | zone_c
];

// charging dock pads
const DOCKS = [
  { x: 1,   z: 17.5, label: "D1" },
  { x: 2.5, z: 17.5, label: "D2" },
];

// desks (decorative boxes) to make the office look occupied
const DESKS = [
  { x: 9,  z: 2 }, { x: 12, z: 2 }, { x: 16, z: 2 }, { x: 20, z: 2 }, { x: 23, z: 2 },
  { x: 9,  z: 6 }, { x: 12, z: 6 }, { x: 16, z: 6 }, { x: 20, z: 6 }, { x: 23, z: 6 },
  { x: 3,  z: 13 }, { x: 6,  z: 13 }, { x: 10, z: 13 },
  { x: 3,  z: 17 }, { x: 6,  z: 17 }, { x: 10, z: 17 },
  { x: 16, z: 13 }, { x: 19, z: 13 }, { x: 22, z: 13 },
  { x: 16, z: 17 }, { x: 19, z: 17 }, { x: 22, z: 17 },
];

// ── sub-components ───────────────────────────────────────────────────────────

function ZoneTile({ zone }: { zone: typeof ZONES[number] }) {
  const cx = zone.x + zone.w / 2;
  const cz = zone.z + zone.d / 2;
  return (
    <group>
      <mesh position={[cx, 0, cz]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[zone.w - 0.05, zone.d - 0.05]} />
        <meshStandardMaterial color={zone.color} roughness={0.9} />
      </mesh>
      <Text
        position={[cx, 0.02, cz]}
        rotation={[-Math.PI / 2, 0, 0]}
        fontSize={0.55}
        color="#94a3b8"
        anchorX="center"
        anchorY="middle"
        maxWidth={zone.w - 0.5}
      >
        {zone.label}
      </Text>
    </group>
  );
}

function WallSegment({ w }: { w: typeof WALLS[number] }) {
  const len = w.len;
  const geo: [number, number, number] = w.axis === "x"
    ? [len, 1.2, 0.12]
    : [0.12, 1.2, len];
  return (
    <mesh position={[w.x, 0.6, w.z]} castShadow>
      <boxGeometry args={geo} />
      <meshStandardMaterial color="#334155" roughness={0.8} />
    </mesh>
  );
}

function DockPad({ dock }: { dock: typeof DOCKS[number] }) {
  return (
    <group position={[dock.x, 0.01, dock.z]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.45, 24]} />
        <meshStandardMaterial color="#78350f" emissive="#92400e" emissiveIntensity={0.4} />
      </mesh>
      <Text position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}
        fontSize={0.3} color="#fbbf24" anchorX="center" anchorY="middle">
        {dock.label}
      </Text>
      <pointLight position={[0, 0.5, 0]} color="#f59e0b" intensity={0.4} distance={1.5} />
    </group>
  );
}

function Desk({ x, z }: { x: number; z: number }) {
  // Legs placed at x=±0.52, z=±0.42 — outside robot body radius (0.38m)
  // so the robot disc slides cleanly under the desk without clipping.
  const LEG_POSITIONS: [number, number][] = [
    [-0.52, -0.42], [0.52, -0.42],
    [-0.52,  0.42], [0.52,  0.42],
  ];
  return (
    <group position={[x, 0, z]}>
      {/* 4 metal legs */}
      {LEG_POSITIONS.map(([lx, lz], i) => (
        <mesh key={i} position={[lx, 0.39, lz]}>
          <boxGeometry args={[0.05, 0.78, 0.05]} />
          <meshStandardMaterial color="#334155" roughness={0.8} metalness={0.4} />
        </mesh>
      ))}
      {/* Tabletop — raised to 0.80 m, well above robot (max 0.26 m) */}
      <mesh position={[0, 0.82, 0]}>
        <boxGeometry args={[1.2, 0.04, 0.95]} />
        <meshStandardMaterial color="#475569" roughness={0.6} />
      </mesh>
      {/* Monitor */}
      <mesh position={[0, 1.17, -0.35]}>
        <boxGeometry args={[0.55, 0.35, 0.03]} />
        <meshStandardMaterial color="#1e293b" emissive="#3b82f6" emissiveIntensity={0.5} />
      </mesh>
    </group>
  );
}

// cleaning trail (ring marks on floor)
function CleaningTrail({ positions }: { positions: [number, number][] }) {
  if (positions.length < 2) return null;
  const pts = positions.map(([x, z]) => new THREE.Vector3(x, 0.02, z));
  return (
    <Line
      points={pts}
      color="#22c55e"
      lineWidth={2}
      opacity={0.35}
      transparent
    />
  );
}

// animated robot model
function RobotMarker({
  robot,
  trail,
}: {
  robot: Robot;
  trail: [number, number][];
}) {
  const bodyRef   = useRef<THREE.Mesh>(null!);
  const brushRef  = useRef<THREE.Mesh>(null!);
  const ringRef   = useRef<THREE.Mesh>(null!);
  const color     = STATUS_COLOR[robot.status] ?? "#6b7280";
  const isCleaning = robot.status === "cleaning";
  const isError    = robot.status === "error";

  useFrame((_, delta) => {
    if (isCleaning && brushRef.current) {
      brushRef.current.rotation.y += delta * 4;
    }
    if (ringRef.current) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (ringRef.current.material as any).opacity =
        0.35 + 0.35 * Math.sin(Date.now() * 0.004);
    }
    if (isError && bodyRef.current) {
      bodyRef.current.rotation.z = 0.08 * Math.sin(Date.now() * 0.008);
    }
  });

  if (!robot.position) return null;
  const { x } = robot.position;
  const z = robot.position.y; // position.y is map-Y mapped to Three.js Z

  return (
    <group position={[x, 0, z]}>
      {/* Cleaning trail */}
      <CleaningTrail positions={trail} />

      {/* Chassis disc */}
      <mesh ref={bodyRef} position={[0, 0.12, 0]} castShadow>
        <cylinderGeometry args={[0.38, 0.38, 0.14, 32]} />
        <meshStandardMaterial color={color} roughness={0.4} metalness={0.3} />
      </mesh>

      {/* Bumper ring */}
      <mesh position={[0, 0.12, 0]}>
        <torusGeometry args={[0.38, 0.04, 8, 32]} />
        <meshStandardMaterial color="#1e293b" roughness={0.8} />
      </mesh>

      {/* Status glow ring */}
      <mesh ref={ringRef} position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.42, 0.56, 32]} />
        <meshStandardMaterial
          color={color}
          transparent
          opacity={0.5}
          side={THREE.DoubleSide}
          emissive={color}
          emissiveIntensity={0.8}
        />
      </mesh>

      {/* Spinning brush (only when cleaning) */}
      {isCleaning && (
        <mesh ref={brushRef} position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.15, 0.35, 6]} />
          <meshStandardMaterial
            color="#86efac"
            transparent
            opacity={0.6}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {/* Top dome / sensor */}
      <mesh position={[0, 0.26, 0]}>
        <sphereGeometry args={[0.12, 16, 8]} />
        <meshStandardMaterial
          color="#0f172a"
          emissive={color}
          emissiveIntensity={isCleaning ? 1.0 : 0.3}
        />
      </mesh>

      {/* Point light under robot while cleaning */}
      {isCleaning && (
        <pointLight position={[0, 0.1, 0]} color={color} intensity={0.8} distance={2.5} />
      )}

      {/* Robot label */}
      <Text
        position={[0, 0.75, 0]}
        fontSize={0.35}
        color="white"
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.04}
        outlineColor="#000000"
      >
        {robot.robot_id.replace("robot_0", "R")}
      </Text>

      {/* Status badge */}
      <Text
        position={[0, 0.5, 0]}
        fontSize={0.22}
        color={color}
        anchorX="center"
        anchorY="middle"
      >
        {robot.status.replace("_", " ")}
      </Text>
    </group>
  );
}

// ── main component ────────────────────────────────────────────────────────────

const MAX_TRAIL = 60;

// keep trails per-robot outside render to avoid re-creating
const trailStore: Record<string, [number, number][]> = {};

interface FleetMapProps {
  robots: Robot[];
}

export function FleetMap({ robots }: FleetMapProps) {
  // update trails
  const trails = useMemo(() => {
    const out: Record<string, [number, number][]> = {};
    for (const r of robots) {
      if (!r.position) continue;
      const key = r.robot_id;
      const pt: [number, number] = [r.position.x, r.position.y];
      const prev = trailStore[key] ?? [];

      if (r.status === "cleaning") {
        const last = prev[prev.length - 1];
        const moved = !last || Math.hypot(pt[0] - last[0], pt[1] - last[1]) > 0.05;
        if (moved) {
          trailStore[key] = [...prev.slice(-MAX_TRAIL), pt];
        }
      } else {
        trailStore[key] = [];
      }
      out[key] = trailStore[key];
    }
    return out;
  }, [robots]);

  const robotsWithPos = robots.filter((r) => r.position);

  return (
    <div className="relative w-full rounded-lg border border-gray-700 overflow-hidden" style={{ height: 480 }}>
      <Canvas
        shadows
        camera={{ position: [12, 22, 28], fov: 45 }}
        style={{ background: "#0f172a" }}
      >
        {/* Lighting */}
        <ambientLight intensity={1.2} />
        <directionalLight
          position={[15, 25, 10]}
          intensity={2.0}
          castShadow
          shadow-mapSize={[1024, 1024]}
        />
        <pointLight position={[12, 8, 10]} color="#ffffff" intensity={1.5} />
        <pointLight position={[5,  6, 5]}  color="#dbeafe" intensity={0.8} />
        <pointLight position={[20, 6, 15]} color="#dbeafe" intensity={0.8} />

        {/* Outer floor */}
        <mesh position={[12.5, -0.01, 10]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[26, 22]} />
          <meshStandardMaterial color="#1e2030" roughness={0.8} />
        </mesh>

        {/* Zone floor tiles */}
        {ZONES.map((z) => <ZoneTile key={z.id} zone={z} />)}

        {/* Walls */}
        {WALLS.map((w, i) => <WallSegment key={i} w={w} />)}

        {/* Desks */}
        {DESKS.map((d, i) => <Desk key={i} {...d} />)}

        {/* Charging docks */}
        {DOCKS.map((d) => <DockPad key={d.label} dock={d} />)}

        {/* Robots */}
        {robotsWithPos.map((r) => (
          <RobotMarker
            key={r.robot_id}
            robot={r}
            trail={trails[r.robot_id] ?? []}
          />
        ))}

        <OrbitControls
          enablePan
          enableZoom
          enableRotate
          minDistance={6}
          maxDistance={55}
          maxPolarAngle={Math.PI / 2.1}
          target={[12, 0, 10]}
        />
      </Canvas>

      {/* Legend overlay */}
      <div className="absolute top-3 right-3 bg-gray-900/85 backdrop-blur rounded-lg p-2.5 text-xs space-y-1.5">
        {Object.entries(STATUS_COLOR).map(([status, color]) => (
          <div key={status} className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
            <span className="text-gray-300 capitalize">{status.replace("_", " ")}</span>
          </div>
        ))}
      </div>

      {/* Stats overlay */}
      <div className="absolute top-3 left-3 bg-gray-900/85 backdrop-blur rounded-lg p-2.5 text-xs">
        <div className="text-gray-400 mb-1 font-semibold">Office Floor 1</div>
        <div className="text-gray-500">
          {robotsWithPos.filter(r => r.status === "cleaning").length} cleaning ·{" "}
          {robotsWithPos.filter(r => r.status === "idle").length} idle ·{" "}
          {robotsWithPos.filter(r => r.status === "charging" || r.status === "docked").length} charging
        </div>
      </div>
    </div>
  );
}
