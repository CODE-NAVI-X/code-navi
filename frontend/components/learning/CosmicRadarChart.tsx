"use client";

import { useMemo, useRef, useState } from "react";
import { Sparkles } from "lucide-react";

export interface CosmicDimension {
  id: string;
  name: string;
  enName: string;
  score: number | null; // null indicates not evaluable / insufficient facts
  level: "卓越" | "稳固" | "良好" | "攻坚" | "起步" | "暂无足够数据";
  description: string;
  basis: string;
}

interface CosmicRadarChartProps {
  dimensions?: CosmicDimension[];
  title?: string;
  subtitle?: string;
  onDimensionClick?: (dimension: CosmicDimension) => void;
  className?: string;
}

const DEFAULT_DIMENSIONS: CosmicDimension[] = [
  {
    id: "concept",
    name: "概念认知",
    enName: "Concepts",
    score: null,
    level: "暂无足够数据",
    description: "核心定义、原理辨析与概念边界掌握",
    basis: "暂无客观题判分或概念诊断记录",
  },
  {
    id: "architecture",
    name: "架构推导",
    enName: "Architecture",
    score: null,
    level: "暂无足够数据",
    description: "拓扑结构、残差连接与模块间信息流推导",
    basis: "暂无网络拓扑与架构推导记录",
  },
  {
    id: "calculation",
    name: "参数计算",
    enName: "Computation",
    score: null,
    level: "暂无足够数据",
    description: "特征图尺寸、感受野与参数量数学推导",
    basis: "暂无参数推导或数值计算记录",
  },
  {
    id: "practice",
    name: "代码实操",
    enName: "Practice",
    score: null,
    level: "暂无足够数据",
    description: "源码调试、网络搭建与在线运行评测",
    basis: "暂无沙盒实操或在线运行评测记录",
  },
  {
    id: "research",
    name: "前沿科研",
    enName: "Research",
    score: null,
    level: "暂无足够数据",
    description: "前沿方向联想、文献精读与课题迁移能力",
    basis: "暂无科研探索会话或文献精读记录",
  },
];

// Helper to provide concise (<50 Chinese characters) description and details
function getDimensionDetailSummary(dim: CosmicDimension): string {
  if (dim.score === null || dim.score === undefined || dim.level === "暂无足够数据") {
    return dim.basis || "当前维度暂无评测记录，完成相关学习实操后自动生成。";
  }
  return dim.basis || dim.description || `${dim.name}维度掌握状态为${dim.level}。`;
}

// 5 vertices positioned radially starting from top (-90 deg)
const ANGLES = [-90, -18, 54, 126, 198]; // degrees
const CENTER_X = 250;
const CENTER_Y = 250;
const MAX_RADIUS = 192;

function polarToCartesian(centerX: number, centerY: number, radius: number, angleInDegrees: number) {
  const angleInRadians = ((angleInDegrees - 0) * Math.PI) / 180.0;
  return {
    x: centerX + radius * Math.cos(angleInRadians),
    y: centerY + radius * Math.sin(angleInRadians),
  };
}

export function CosmicRadarChart({
  dimensions = DEFAULT_DIMENSIONS,
  onDimensionClick,
  className = "",
}: CosmicRadarChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // 3D mouse tilt state
  const containerRef = useRef<HTMLDivElement>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const xPos = (e.clientX - rect.left) / rect.width;
    const yPos = (e.clientY - rect.top) / rect.height;
    const maxTilt = 10;
    const tiltX = (yPos - 0.5) * -maxTilt;
    const tiltY = (xPos - 0.5) * maxTilt;
    setTilt({ x: tiltX, y: tiltY });
  };

  const handleMouseLeave = () => {
    setTilt({ x: 0, y: 0 });
    setHoveredIndex(null);
  };

  // Normalized dimensions (guaranteed length 5)
  const dims = useMemo(() => {
    return DEFAULT_DIMENSIONS.map((def, idx) => {
      const custom = dimensions.find((d) => d.id === def.id) || dimensions[idx];
      return custom || def;
    });
  }, [dimensions]);

  // Overall score: only over dimensions that have facts/scores
  const overallScore = useMemo(() => {
    const evaluable = dims.filter((d) => d.score !== null && d.score !== undefined);
    if (evaluable.length === 0) return null;
    return Math.round(
      evaluable.reduce((acc, cur) => acc + (cur.score as number), 0) / evaluable.length
    );
  }, [dims]);

  // Coordinates for the polygon vertices (null if not evaluable)
  const polygonPoints = useMemo(() => {
    return dims.map((dim, idx) => {
      const angle = ANGLES[idx];
      if (dim.score === null || dim.score === undefined) {
        return null;
      }
      const r = (Math.max(12, Math.min(100, dim.score)) / 100) * MAX_RADIUS;
      return polarToCartesian(CENTER_X, CENTER_Y, r, angle);
    });
  }, [dims]);

  const evaluableCount = useMemo(() => {
    return dims.filter((d) => d.score !== null && d.score !== undefined).length;
  }, [dims]);

  const polygonPath = useMemo(() => {
    if (evaluableCount < 3) return "";
    const validPts = polygonPoints.filter((p): p is { x: number; y: number } => p !== null);
    if (validPts.length < 3) return "";
    return (
      validPts.map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(" ") +
      " Z"
    );
  }, [polygonPoints, evaluableCount]);

  // Label coordinates (outside max radius)
  const labelPositions = useMemo(() => {
    return ANGLES.map((angle) => polarToCartesian(CENTER_X, CENTER_Y, MAX_RADIUS + 28, angle));
  }, []);

  // Background orbital rings radii
  const rings = [0.2, 0.4, 0.6, 0.8, 1.0];

  // Constant decorative background stars
  const backgroundStars = useMemo(() => {
    return [
      { x: 75, y: 80, r: 1.2, o: 0.6 },
      { x: 420, y: 95, r: 1.5, o: 0.7 },
      { x: 90, y: 390, r: 1.0, o: 0.5 },
      { x: 410, y: 370, r: 1.4, o: 0.8 },
      { x: 240, y: 45, r: 1.1, o: 0.5 },
      { x: 30, y: 220, r: 0.9, o: 0.4 },
      { x: 470, y: 260, r: 1.3, o: 0.7 },
      { x: 160, y: 140, r: 0.8, o: 0.3 },
      { x: 340, y: 320, r: 1.0, o: 0.4 },
    ];
  }, []);

  // Render a dimension text card
  const renderDimensionCard = (dim: CosmicDimension, idx: number, cardClassName = "") => {
    const isHovered = hoveredIndex === idx;
    const isEvaluable = dim.score !== null && dim.score !== undefined && dim.level !== "暂无足够数据";
    const detailSummary = getDimensionDetailSummary(dim);
    const levelColor = !isEvaluable
      ? "text-slate-400 border-slate-700/60 bg-slate-800/40"
      : dim.level === "卓越"
      ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
      : dim.level === "稳固"
      ? "text-sky-400 border-sky-500/30 bg-sky-500/10"
      : dim.level === "良好"
      ? "text-indigo-300 border-indigo-500/30 bg-indigo-500/10"
      : dim.level === "攻坚"
      ? "text-rose-400 border-rose-500/30 bg-rose-500/10"
      : "text-amber-400 border-amber-500/30 bg-amber-500/10";

    const dotColor = !isEvaluable
      ? "bg-slate-500"
      : (dim.score ?? 0) >= 75
      ? "bg-emerald-400"
      : (dim.score ?? 0) >= 60
      ? "bg-cyan-400"
      : "bg-rose-400";

    return (
      <div
        key={`card-${dim.id}`}
        onMouseEnter={() => setHoveredIndex(idx)}
        onMouseLeave={() => setHoveredIndex(null)}
        onClick={() => onDimensionClick?.(dim)}
        className={`cursor-pointer rounded-2xl border p-4 transition-all duration-200 backdrop-blur-md ${
          isHovered
            ? "border-cyan-400/60 bg-slate-800/90 shadow-lg shadow-cyan-500/20 scale-[1.02]"
            : "border-slate-800/80 bg-slate-900/65 hover:border-slate-700 hover:bg-slate-800/70"
        } ${cardClassName}`}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
            <span className="text-sm font-bold text-white tracking-wide">{dim.name}</span>
          </div>
          <span className={`rounded-md border px-2.5 py-0.5 text-xs font-bold ${levelColor}`}>
            {isEvaluable ? `${dim.score}分 · ${dim.level}` : "暂无足够数据"}
          </span>
        </div>
        <p className="mt-2.5 text-xs leading-relaxed text-slate-200">
          {detailSummary}
        </p>
      </div>
    );
  };

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={`relative overflow-hidden rounded-3xl border border-indigo-500/20 bg-gradient-to-b from-[#0b0f19] via-[#0f172a] to-[#0a0e1a] p-6 text-white shadow-2xl ${className}`}
    >
      {/* Background celestial ambient glow */}
      <div className="pointer-events-none absolute -top-24 -left-24 h-72 w-72 rounded-full bg-cyan-500/10 blur-[90px]" />
      <div className="pointer-events-none absolute -bottom-24 -right-24 h-72 w-72 rounded-full bg-violet-600/15 blur-[90px]" />

      {/* Simplified Top Header: Clean and focused on overall score */}
      <div className="relative z-10 flex items-center justify-center border-b border-slate-800/80 pb-4">
        <div className="flex items-center gap-2 rounded-2xl bg-slate-800/80 px-5 py-2 text-sm text-slate-200 border border-slate-700/60 shadow-inner">
          <Sparkles className="h-4 w-4 text-cyan-400" />
          <span className="font-medium text-slate-300">综合能力得分：</span>
          {overallScore !== null ? (
            <span className="text-xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400">
              {overallScore}分
            </span>
          ) : (
            <span className="text-sm font-semibold text-slate-400">
              待评测（暂无足够数据）
            </span>
          )}
        </div>
      </div>

      {/* 3-Column HUD Layout: Left 2 Cards, Center Radar + Top Card, Right 2 Cards */}
      <div className="relative mt-4 grid grid-cols-1 items-stretch gap-6 lg:grid-cols-12">
        {/* Left Column: 前沿科研 (top-left) & 代码实操 (pushed down next to bottom-left label) */}
        <div className="flex flex-col justify-between py-2 lg:col-span-3">
          <div className="mt-8">
            {renderDimensionCard(dims[4], 4)} {/* 前沿科研 */}
          </div>
          <div className="mt-auto mb-3">
            {renderDimensionCard(dims[3], 3)} {/* 代码实操 */}
          </div>
        </div>

        {/* Center Column: 概念认知 (top card) + Radar SVG with 3D Mouse Tilt */}
        <div className="flex flex-col items-center lg:col-span-6">
          {/* Top Card: 概念认知 */}
          <div className="w-full max-w-sm mb-2">
            {renderDimensionCard(dims[0], 0)}
          </div>

          {/* SVG Radar Compass with 3D Tilt */}
          <div
            style={{
              transform: `perspective(1000px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
              transition: "transform 0.15s ease-out",
            }}
            className="relative flex w-full items-center justify-center py-1"
          >
            <svg
              viewBox="-80 0 660 500"
              className="h-auto w-full max-w-[580px] select-none overflow-visible"
              aria-label="认知能力星轨雷达图"
            >
              <defs>
                {/* Radial glow filter for the constellation polygon */}
                <filter id="cosmicGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="6" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>

                {/* Pulsing star node glow */}
                <filter id="starGlow" x="-40%" y="-40%" width="180%" height="180%">
                  <feGaussianBlur stdDeviation="3" result="glow" />
                  <feComposite in="SourceGraphic" in2="glow" operator="over" />
                </filter>

                {/* Aurora polygon fill gradient */}
                <radialGradient id="nebulaGradient" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.65" />
                  <stop offset="50%" stopColor="#6366f1" stopOpacity="0.45" />
                  <stop offset="90%" stopColor="#a855f7" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.05" />
                </radialGradient>

                {/* Ring gradient */}
                <linearGradient id="ringGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.3" />
                  <stop offset="50%" stopColor="#818cf8" stopOpacity="0.15" />
                  <stop offset="100%" stopColor="#c084fc" stopOpacity="0.3" />
                </linearGradient>
              </defs>

              {/* Background starry particles */}
              {backgroundStars.map((star, i) => (
                <circle
                  key={`bg-star-${i}`}
                  cx={star.x}
                  cy={star.y}
                  r={star.r}
                  fill="#ffffff"
                  opacity={star.o}
                />
              ))}

              {/* Concentric orbital rings */}
              {rings.map((factor, i) => {
                const r = MAX_RADIUS * factor;
                const isOuter = i === rings.length - 1;
                return (
                  <g key={`ring-${i}`}>
                    <circle
                      cx={CENTER_X}
                      cy={CENTER_Y}
                      r={r}
                      fill="none"
                      stroke="url(#ringGradient)"
                      strokeWidth={isOuter ? "1.5" : "1"}
                      strokeDasharray={isOuter ? "4, 4" : undefined}
                      opacity={0.8}
                    />
                    {/* Orbital percentage marker */}
                    {factor < 1.0 && (
                      <text
                        x={CENTER_X + 4}
                        y={CENTER_Y - r + 10}
                        fill="#64748b"
                        fontSize="9"
                        fontFamily="monospace"
                        opacity={0.7}
                      >
                        {Math.round(factor * 100)}
                      </text>
                    )}
                  </g>
                );
              })}

              {/* Radial axis rays */}
              {ANGLES.map((angle, i) => {
                const endpoint = polarToCartesian(CENTER_X, CENTER_Y, MAX_RADIUS + 8, angle);
                const isHovered = hoveredIndex === i;
                return (
                  <line
                    key={`axis-${i}`}
                    x1={CENTER_X}
                    y1={CENTER_Y}
                    x2={endpoint.x}
                    y2={endpoint.y}
                    stroke={isHovered ? "#38bdf8" : "#334155"}
                    strokeWidth={isHovered ? "2" : "1"}
                    strokeDasharray={isHovered ? undefined : "2, 3"}
                    opacity={isHovered ? 1 : 0.6}
                    className="transition-all duration-300"
                  />
                );
              })}

              {/* Constellation polygon fill & stroke (only if at least 3 evaluable dimensions) */}
              {polygonPath && (
                <>
                  <polygon
                    points={polygonPoints
                      .filter((p): p is { x: number; y: number } => p !== null)
                      .map((p) => `${p.x},${p.y}`)
                      .join(" ")}
                    fill="url(#nebulaGradient)"
                    stroke="#a855f7"
                    strokeWidth="2"
                    filter="url(#cosmicGlow)"
                    className="transition-all duration-500 ease-out"
                  />
                  {/* Second highlight perimeter wire */}
                  <path
                    d={polygonPath}
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="1.5"
                    opacity={0.7}
                    className="transition-all duration-500 ease-out"
                  />
                </>
              )}

              {/* Center core pulse */}
              <circle cx={CENTER_X} cy={CENTER_Y} r="5" fill="#38bdf8" opacity="0.8" />
              <circle cx={CENTER_X} cy={CENTER_Y} r="12" fill="#818cf8" opacity="0.25" />

              {/* Star nodes (vertices) - only for evaluable dimensions */}
              {polygonPoints.map((pt, i) => {
                if (!pt) return null;
                const isHovered = hoveredIndex === i;
                const dim = dims[i];
                return (
                  <g
                    key={`node-${i}`}
                    className="cursor-pointer transition-transform duration-300"
                    onMouseEnter={() => setHoveredIndex(i)}
                    onMouseLeave={() => setHoveredIndex(null)}
                    onClick={() => onDimensionClick?.(dim)}
                  >
                    {/* Ripple halo when hovered */}
                    {isHovered && (
                      <circle
                        cx={pt.x}
                        cy={pt.y}
                        r="14"
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth="1.5"
                        opacity={0.8}
                        className="animate-ping origin-center"
                      />
                    )}
                    {/* Outer star glow ring */}
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r={isHovered ? "9" : "6"}
                      fill={isHovered ? "#38bdf8" : "#8b5cf6"}
                      opacity={isHovered ? 0.9 : 0.6}
                      filter="url(#starGlow)"
                      className="transition-all duration-200"
                    />
                    {/* Inner star core point */}
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r={isHovered ? "4" : "3"}
                      fill="#ffffff"
                      className="transition-all duration-200"
                    />
                  </g>
                );
              })}

              {/* Enlarged aesthetic external dimension labels */}
              {dims.map((dim, i) => {
                const pos = labelPositions[i];
                const isHovered = hoveredIndex === i;
                const isEvaluable = dim.score !== null && dim.score !== undefined && dim.level !== "暂无足够数据";

                let textAnchor: "start" | "middle" | "end" = "middle";
                if (pos.x < CENTER_X - 25) textAnchor = "end";
                else if (pos.x > CENTER_X + 25) textAnchor = "start";

                const levelColor = !isEvaluable
                  ? "#64748b"
                  : dim.level === "卓越"
                  ? "#34d399"
                  : dim.level === "稳固"
                  ? "#38bdf8"
                  : dim.level === "良好"
                  ? "#818cf8"
                  : dim.level === "攻坚"
                  ? "#f43f5e"
                  : "#fbbf24";

                return (
                  <g
                    key={`label-${i}`}
                    className="cursor-pointer transition-all duration-300 select-none"
                    onMouseEnter={() => setHoveredIndex(i)}
                    onMouseLeave={() => setHoveredIndex(null)}
                    onClick={() => onDimensionClick?.(dim)}
                  >
                    <text
                      x={pos.x}
                      y={pos.y - 8}
                      textAnchor={textAnchor}
                      fill={isHovered ? "#38bdf8" : isEvaluable ? "#f8fafc" : "#94a3b8"}
                      fontSize="15"
                      fontWeight="700"
                      letterSpacing="0.04em"
                    >
                      {dim.name}
                    </text>
                    <text
                      x={pos.x}
                      y={pos.y + 11}
                      textAnchor={textAnchor}
                      fill={levelColor}
                      fontSize="12"
                      fontFamily="monospace"
                      fontWeight="700"
                    >
                      {isEvaluable ? `${dim.score}分 · ${dim.level}` : "暂无足够数据"}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* Right Column: 架构推导 (top-right) & 参数计算 (pushed down next to bottom-right label) */}
        <div className="flex flex-col justify-between py-2 lg:col-span-3">
          <div className="mt-8">
            {renderDimensionCard(dims[1], 1)} {/* 架构推导 */}
          </div>
          <div className="mt-auto mb-3">
            {renderDimensionCard(dims[2], 2)} {/* 参数计算 */}
          </div>
        </div>
      </div>
    </div>
  );
}
