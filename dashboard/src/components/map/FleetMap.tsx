import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid, Text } from "@react-three/drei";
import type { Robot } from "../../types";

const STATUS_COLORS: Record<string, string> = {
  offline:  "#6b7280",
  idle:     "#3b82f6",
  cleaning: "#22c55e",
  charging: "#eab308",
  docked:   "#a16207",
  error:    "#ef4444",
  ota_update: "#a855f7",
};

function RobotMarker({ robot }: { robot: Robot }) {
  if (!robot.position) return null;
  const color = STATUS_COLORS[robot.status] || "#6b7280";

  return (
    <group position={[robot.position.x, 0, robot.position.y]}>
      {/* Robot body */}
      <mesh>
        <cylinderGeometry args={[0.3, 0.3, 0.2, 16]} />
        <meshStandardMaterial color={color} />
      </mesh>
      {/* Direction indicator */}
      <mesh position={[0.3, 0.15, 0]}>
        <coneGeometry args={[0.1, 0.3, 8]} rotation={[0, 0, -Math.PI / 2]} />
        <meshStandardMaterial color={color} />
      </mesh>
      {/* Robot ID label */}
      <Text
        position={[0, 0.6, 0]}
        fontSize={0.4}
        color="white"
        anchorX="center"
        anchorY="middle"
      >
        {robot.robot_id.replace("robot_", "R")}
      </Text>
    </group>
  );
}

interface FleetMapProps {
  robots: Robot[];
  mapWidth?: number;
  mapHeight?: number;
}

export function FleetMap({ robots, mapWidth = 25, mapHeight = 20 }: FleetMapProps) {
  const onlineRobots = robots.filter((r) => r.position);

  return (
    <div className="w-full h-96 bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      <Canvas
        camera={{ position: [mapWidth / 2, 20, mapHeight + 10], fov: 50 }}
        style={{ background: "#0f1117" }}
      >
        <ambientLight intensity={0.6} />
        <directionalLight position={[10, 20, 10]} intensity={0.8} />

        {/* Floor grid */}
        <Grid
          position={[mapWidth / 2, 0, mapHeight / 2]}
          args={[mapWidth, mapHeight]}
          cellSize={1}
          cellThickness={0.5}
          cellColor="#1f2937"
          sectionSize={5}
          sectionThickness={1}
          sectionColor="#374151"
          fadeDistance={60}
          fadeStrength={1}
          infiniteGrid={false}
        />

        {/* Floor plane */}
        <mesh position={[mapWidth / 2, -0.01, mapHeight / 2]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[mapWidth, mapHeight]} />
          <meshStandardMaterial color="#111827" />
        </mesh>

        {/* Robots */}
        {onlineRobots.map((robot) => (
          <RobotMarker key={robot.robot_id} robot={robot} />
        ))}

        <OrbitControls
          enablePan
          enableZoom
          enableRotate
          minDistance={5}
          maxDistance={60}
          maxPolarAngle={Math.PI / 2.2}
        />
      </Canvas>

      {/* Legend */}
      <div className="absolute bottom-4 right-4 bg-gray-900/80 rounded-lg p-2 text-xs space-y-1">
        {Object.entries(STATUS_COLORS).map(([status, color]) => (
          <div key={status} className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-gray-300 capitalize">{status.replace("_", " ")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
