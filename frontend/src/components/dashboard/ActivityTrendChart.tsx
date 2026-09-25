import React, { useState, useMemo } from "react";
import type { DashboardActivityPoint } from "../../types/dashboard";

interface ActivityTrendChartProps {
  points: DashboardActivityPoint[];
  isLoading?: boolean;
}

interface ChartPoint {
  key: string;
  date: string;
  label: string;
  fullLabel: string;
  sent: number;
  responses: number;
  bounced: number;
}

const MONTH_NAMES_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
];

const MONTH_NAMES_FULL = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

function parseDate(dStr: string): { year: number; month: number; day: number } {
  const parts = dStr.split("-").map(Number);
  return {
    year: parts[0] || 2026,
    month: parts[1] || 1,
    day: parts[2] || 1,
  };
}

/**
 * Adaptively aggregates raw daily activity points into an optimal number of chart points.
 * - <= 31 days (Today, 7d, 30d): Keep daily resolution.
 * - 32 to 210 days (90d, 6m): Aggregate into 7-day weekly buckets (~13 to 26 points).
 * - > 210 days (1y, All Time): Aggregate into calendar month buckets (~12 to 25 points).
 *
 * All sums (sent, responses, bounced) are strictly preserved across buckets with zero data loss.
 */
function aggregateActivityPoints(rawPoints: DashboardActivityPoint[]): ChartPoint[] {
  if (!rawPoints || rawPoints.length === 0) return [];
  const n = rawPoints.length;

  // Case 1: Short ranges (<= 31 days) -> Keep daily points
  if (n <= 31) {
    return rawPoints.map((p) => {
      const { year, month, day } = parseDate(p.date);
      const shortLabel = n <= 7 && p.label ? p.label : `${MONTH_NAMES_SHORT[month - 1]} ${day}`;
      const fullLabel = `${MONTH_NAMES_FULL[month - 1]} ${day}, ${year}`;
      return {
        key: p.date,
        date: p.date,
        label: shortLabel,
        fullLabel,
        sent: p.sent,
        responses: p.responses,
        bounced: p.bounced,
      };
    });
  }

  // Case 2: Medium ranges (32 to 210 days) -> 7-day weekly buckets
  if (n <= 210) {
    const chunkSize = 7;
    const aggregated: ChartPoint[] = [];

    for (let i = 0; i < n; i += chunkSize) {
      const slice = rawPoints.slice(i, i + chunkSize);
      const startPt = slice[0];
      const endPt = slice[slice.length - 1];

      const startParsed = parseDate(startPt.date);
      const endParsed = parseDate(endPt.date);

      const sentSum = slice.reduce((acc, cur) => acc + cur.sent, 0);
      const respSum = slice.reduce((acc, cur) => acc + cur.responses, 0);
      const bounceSum = slice.reduce((acc, cur) => acc + cur.bounced, 0);

      const label = `${MONTH_NAMES_SHORT[startParsed.month - 1]} ${startParsed.day}`;
      const fullLabel = `${MONTH_NAMES_SHORT[startParsed.month - 1]} ${startParsed.day} – ${MONTH_NAMES_SHORT[endParsed.month - 1]} ${endParsed.day}, ${endParsed.year}`;

      aggregated.push({
        key: `week-${startPt.date}`,
        date: startPt.date,
        label,
        fullLabel,
        sent: sentSum,
        responses: respSum,
        bounced: bounceSum,
      });
    }

    return aggregated;
  }

  // Case 3: Long ranges (> 210 days) -> Calendar month buckets
  const monthMap = new Map<
    string,
    {
      year: number;
      month: number;
      sent: number;
      responses: number;
      bounced: number;
      firstDate: string;
    }
  >();

  for (const pt of rawPoints) {
    const { year, month } = parseDate(pt.date);
    const monthKey = `${year}-${String(month).padStart(2, "0")}`;
    const existing = monthMap.get(monthKey);
    if (!existing) {
      monthMap.set(monthKey, {
        year,
        month,
        sent: pt.sent,
        responses: pt.responses,
        bounced: pt.bounced,
        firstDate: pt.date,
      });
    } else {
      existing.sent += pt.sent;
      existing.responses += pt.responses;
      existing.bounced += pt.bounced;
    }
  }

  const years = new Set(Array.from(monthMap.values()).map((m) => m.year));
  const isMultiYear = years.size > 1;

  const aggregated: ChartPoint[] = [];
  for (const [key, data] of monthMap.entries()) {
    const label = isMultiYear
      ? `${MONTH_NAMES_SHORT[data.month - 1]} '${String(data.year).slice(-2)}`
      : MONTH_NAMES_SHORT[data.month - 1];
    const fullLabel = `${MONTH_NAMES_FULL[data.month - 1]} ${data.year}`;

    aggregated.push({
      key,
      date: data.firstDate,
      label,
      fullLabel,
      sent: data.sent,
      responses: data.responses,
      bounced: data.bounced,
    });
  }

  return aggregated;
}

export function ActivityTrendChart({ points, isLoading }: ActivityTrendChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const chartPoints = useMemo(() => {
    return aggregateActivityPoints(points || []);
  }, [points]);

  if (isLoading) {
    return (
      <div className="h-64 w-full flex items-center justify-center bg-slate-50/50 rounded-xl border border-slate-100 animate-pulse">
        <div className="flex flex-col items-center space-y-2">
          <div className="h-4 w-32 bg-slate-200 rounded"></div>
          <div className="h-3 w-48 bg-slate-200/70 rounded"></div>
        </div>
      </div>
    );
  }

  const n = chartPoints.length;
  const maxVal = Math.max(
    ...chartPoints.map((p) => Math.max(p.sent, p.responses, p.bounced)),
    5 // Minimum scale ceiling so 0 isn't collapsed
  );

  const width = 800;
  const height = 240;
  const paddingX = 45;
  const paddingBottom = 40;
  const paddingTop = 30;
  const chartWidth = width - paddingX * 2;
  const chartHeight = height - paddingTop - paddingBottom;

  const getX = (idx: number) => {
    if (n <= 1) return width / 2;
    return paddingX + (idx / (n - 1)) * chartWidth;
  };

  const getY = (val: number) => {
    const ratio = Math.min(1, Math.max(0, val / maxVal));
    return height - paddingBottom - ratio * chartHeight;
  };

  // Build smooth cubic bezier path
  const buildSmoothPath = (values: number[]) => {
    if (values.length === 0) return "";
    const pts = values.map((v, i) => ({ x: getX(i), y: getY(v) }));
    if (pts.length === 1) {
      return `M ${paddingX} ${pts[0].y} L ${width - paddingX} ${pts[0].y}`;
    }

    let path = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i === 0 ? 0 : i - 1];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2 < pts.length ? i + 2 : i + 1];

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      path += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }
    return path;
  };

  const sentPath = buildSmoothPath(chartPoints.map((p) => p.sent));
  const respPath = buildSmoothPath(chartPoints.map((p) => p.responses));
  const bouncePath = buildSmoothPath(chartPoints.map((p) => p.bounced));

  // Area under curve paths
  const baselineY = height - paddingBottom;
  const buildAreaPath = (linePath: string) => {
    if (!linePath || chartPoints.length === 0) return "";
    const firstX = chartPoints.length === 1 ? paddingX : getX(0);
    const lastX = chartPoints.length === 1 ? width - paddingX : getX(chartPoints.length - 1);
    return `${linePath} L ${lastX} ${baselineY} L ${firstX} ${baselineY} Z`;
  };

  const sentArea = buildAreaPath(sentPath);
  const respArea = buildAreaPath(respPath);

  const activePoint =
    hoverIndex !== null && chartPoints[hoverIndex] ? chartPoints[hoverIndex] : null;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const svgX = (clientX / rect.width) * width;

    let closestIdx = 0;
    let minDiff = Infinity;
    chartPoints.forEach((_, idx) => {
      const diff = Math.abs(getX(idx) - svgX);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = idx;
      }
    });
    setHoverIndex(closestIdx);
  };

  const allZero = chartPoints.every(
    (p) => p.sent === 0 && p.responses === 0 && p.bounced === 0
  );

  return (
    <div className="w-full relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto overflow-visible select-none"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <defs>
          <linearGradient id="sentGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.0" />
          </linearGradient>
          <linearGradient id="respGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.0" />
          </linearGradient>
          <linearGradient id="bounceGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Horizontal grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const y = height - paddingBottom - tick * chartHeight;
          return (
            <line
              key={tick}
              x1={paddingX}
              y1={y}
              x2={width - paddingX}
              y2={y}
              stroke="#f1f5f9"
              strokeWidth="1"
              strokeDasharray={tick === 0 ? "none" : "3 3"}
            />
          );
        })}

        {/* Area Fills */}
        {sentArea && <path d={sentArea} fill="url(#sentGradient)" />}
        {respArea && <path d={respArea} fill="url(#respGradient)" />}

        {/* Smooth Series Lines */}
        {bouncePath && (
          <path
            d={bouncePath}
            fill="none"
            stroke="#f43f5e"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-all duration-300"
          />
        )}
        {respPath && (
          <path
            d={respPath}
            fill="none"
            stroke="#0ea5e9"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-all duration-300"
          />
        )}
        {sentPath && (
          <path
            d={sentPath}
            fill="none"
            stroke="#6366f1"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-all duration-300"
          />
        )}

        {/* Date Labels on X Axis */}
        {chartPoints.map((p, idx) => {
          const maxLabels = 8;
          const step = Math.max(1, Math.floor(chartPoints.length / maxLabels));
          const isFirst = idx === 0;
          const isLast = idx === chartPoints.length - 1;
          const isStepped = idx % step === 0;
          const showLabel = isFirst || isLast || isStepped;

          // Prevent rendering penultimate label if it is too close to the last one
          if (!isFirst && !isLast && isStepped && idx >= chartPoints.length - Math.ceil(step / 1.5)) {
            return null;
          }

          if (!showLabel && hoverIndex !== idx) return null;
          const x = getX(idx);
          const isSelected = hoverIndex === idx;
          return (
            <text
              key={p.key}
              x={x}
              y={height - 12}
              textAnchor="middle"
              className={`text-[11px] transition-colors duration-150 select-none ${
                isSelected ? "fill-indigo-700 font-semibold" : "fill-slate-400 font-medium"
              }`}
            >
              {p.label}
            </text>
          );
        })}

        {/* Active Hover Indicator Line & Markers */}
        {hoverIndex !== null && activePoint && (
          <g>
            <line
              x1={getX(hoverIndex)}
              y1={paddingTop - 10}
              x2={getX(hoverIndex)}
              y2={baselineY}
              stroke="#94a3b8"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
            {/* Sent marker dot */}
            <circle
              cx={getX(hoverIndex)}
              cy={getY(activePoint.sent)}
              r="4.5"
              fill="#6366f1"
              stroke="#ffffff"
              strokeWidth="2"
              className="drop-shadow-sm"
            />
            {/* Response marker dot */}
            <circle
              cx={getX(hoverIndex)}
              cy={getY(activePoint.responses)}
              r="4.5"
              fill="#0ea5e9"
              stroke="#ffffff"
              strokeWidth="2"
              className="drop-shadow-sm"
            />
            {/* Bounced marker dot */}
            <circle
              cx={getX(hoverIndex)}
              cy={getY(activePoint.bounced)}
              r="4.5"
              fill="#f43f5e"
              stroke="#ffffff"
              strokeWidth="2"
              className="drop-shadow-sm"
            />
          </g>
        )}
      </svg>

      {/* Floating Tooltip with boundary-safe positioning */}
      {hoverIndex !== null && activePoint && (
        <div
          className="absolute z-20 pointer-events-none transition-all duration-75"
          style={{
            left: `${Math.max(5, Math.min(95, (getX(hoverIndex) / width) * 100))}%`,
            top: "8px",
            transform:
              getX(hoverIndex) / width > 0.75
                ? "translateX(-95%)"
                : getX(hoverIndex) / width < 0.25
                ? "translateX(-5%)"
                : "translateX(-50%)",
          }}
        >
          <div className="bg-slate-900/95 text-white text-[11px] rounded-xl px-3.5 py-2 shadow-xl backdrop-blur-xs border border-slate-700 flex items-center space-x-3 whitespace-nowrap">
            <span className="font-semibold text-slate-200">{activePoint.fullLabel}</span>
            <span className="h-3 w-px bg-slate-700" />
            <span className="text-indigo-300 font-medium">
              Sent: <strong className="text-white">{activePoint.sent.toLocaleString()}</strong>
            </span>
            <span className="text-sky-300 font-medium">
              Resp: <strong className="text-white">{activePoint.responses.toLocaleString()}</strong>
            </span>
            <span className="text-rose-300 font-medium">
              Bounced: <strong className="text-white">{activePoint.bounced.toLocaleString()}</strong>
            </span>
          </div>
        </div>
      )}

      {/* Empty State Overlay if 0 data across period */}
      {allZero && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/40 backdrop-blur-[0.5px]">
          <span className="text-xs text-slate-400 bg-white/80 px-3 py-1.5 rounded-full border border-slate-200/80 shadow-xs">
            No activity recorded during this period
          </span>
        </div>
      )}
    </div>
  );
}
