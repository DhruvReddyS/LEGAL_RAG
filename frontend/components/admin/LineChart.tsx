"use client";

import { useId, useState, type PointerEvent as ReactPointerEvent } from "react";
import { chartGeometry, nearestPoint, type ChartPoint, type PlacedPoint } from "@/lib/admin-presentation";

const BOX = { width: 560, height: 190, left: 46, right: 14, top: 12, bottom: 28 };

/**
 * One measure on one axis. A second measure gets its own chart, never a second
 * scale. A missing day is a gap, not a line drawn across it, and a table carries
 * the same values for anyone who cannot use the plot.
 */
export function LineChart({
  title,
  unit,
  data,
  max,
  format,
  emptyLabel = "Nothing measured in this period",
}: {
  title: string;
  unit: string;
  data: ChartPoint[];
  max?: number;
  format: (value: number | null) => string;
  emptyLabel?: string;
}) {
  const titleId = useId();
  const [active, setActive] = useState<PlacedPoint | null>(null);
  const chart = chartGeometry(data, BOX, { max });
  const latest = [...data].reverse().find(item => item.value !== null);

  const move = (event: ReactPointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width) return;
    setActive(nearestPoint(chart.points, ((event.clientX - rect.left) / rect.width) * BOX.width));
  };

  return (
    <figure className="admin-chart">
      <figcaption>
        <strong id={titleId}>{title}</strong>
        <span>{unit}</span>
        {latest && <b>{format(latest.value)}</b>}
      </figcaption>
      {chart.hasData ? (
        <div className="admin-chart-plot">
          <svg
            viewBox={`0 0 ${BOX.width} ${BOX.height}`}
            role="img"
            aria-labelledby={titleId}
            onPointerMove={move}
            onPointerLeave={() => setActive(null)}
          >
            {chart.ticks.map(tick => (
              <g key={tick.value}>
                <line className="admin-chart-grid" x1={BOX.left} x2={BOX.width - BOX.right} y1={tick.y} y2={tick.y} />
                <text className="admin-chart-axis" x={BOX.left - 7} y={tick.y + 3} textAnchor="end">
                  {format(tick.value)}
                </text>
              </g>
            ))}
            {chart.xLabels.map((label, index) => (
              <text
                key={`${label.label}-${index}`}
                className="admin-chart-axis"
                x={label.x}
                y={BOX.height - 9}
                textAnchor={index === 0 && chart.xLabels.length > 1 ? "start" : index === chart.xLabels.length - 1 && chart.xLabels.length > 1 ? "end" : "middle"}
              >
                {label.label}
              </text>
            ))}
            {chart.segments.map(path => <path key={path} className="admin-chart-line" d={path} />)}
            {chart.points.map(point =>
              point.y === null ? null : <circle key={`${point.label}-${point.x}`} className="admin-chart-dot" cx={point.x} cy={point.y} r={active === point ? 5 : 3.5} />,
            )}
            {active && active.y !== null && (
              <line className="admin-chart-cross" x1={active.x} x2={active.x} y1={BOX.top} y2={BOX.height - BOX.bottom} />
            )}
          </svg>
          {active && (
            <div
              className="admin-chart-tip"
              style={{ left: `${(active.x / BOX.width) * 100}%`, transform: active.x > BOX.width * 0.6 ? "translateX(-100%)" : "none" }}
            >
              <strong>{format(active.value)}</strong>
              <span>{active.label}</span>
              {active.detail && <small>{active.detail}</small>}
            </div>
          )}
        </div>
      ) : (
        <p className="admin-empty">{emptyLabel}</p>
      )}
      {chart.hasData && (
        <details className="admin-chart-table">
          <summary>View as a table</summary>
          <div className="admin-table-scroll">
            <table className="admin-table">
              <thead><tr><th scope="col">When</th><th scope="col">{title}</th><th scope="col">Run</th></tr></thead>
              <tbody>
                {data.map((item, index) => (
                  <tr key={`${item.label}-${index}`}><td>{item.label}</td><td>{format(item.value)}</td><td>{item.detail ?? ""}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  );
}
