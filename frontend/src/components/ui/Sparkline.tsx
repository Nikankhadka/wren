/**
 * docs/design/frontend.md section 6: a dependency-free inline-SVG sparkline for
 * the T-034 dashboards 30-day cost trend. No chart library - just a polyline
 * (plus an optional low-opacity area fill) drawn on a fixed 100x28 viewBox and
 * stretched to fit its container via `preserveAspectRatio="none"`.
 *
 * Colour comes entirely from the token system: the wrapper carries `text-accent`
 * and the SVG strokes/fills with `currentColor`, so there is not a single colour
 * literal in this file. The stroke stays crisp under the non-uniform scale via
 * `vectorEffect="non-scaling-stroke"`.
 */

const VIEW_W = 100;
const VIEW_H = 28;
// Vertical breathing room so a peak or trough stroke is never clipped.
const PAD_Y = 2;

export interface SparklineProps {
  /** The series to plot, oldest-first. */
  points: number[];
  /** Human label prefixed to the computed aria summary (e.g. "30-day daily cost"). */
  label?: string;
  /** Formats each value inside the aria summary. Defaults to `String`. */
  format?: (value: number) => string;
  className?: string;
}

/**
 * Maps a value onto the vertical axis (inverted: larger value -> smaller y).
 * A zero-range series (all-equal, single point, empty) sits on a flat baseline
 * along the bottom rather than dividing by zero.
 */
function projectY(value: number, min: number, range: number): number {
  if (range === 0) return VIEW_H - PAD_Y;
  const usable = VIEW_H - PAD_Y * 2;
  return PAD_Y + usable * (1 - (value - min) / range);
}

export function Sparkline({ points, label, format = String, className }: SparklineProps) {
  const prefix = label ?? "Trend";
  const n = points.length;

  if (n === 0) {
    return (
      <span className={`block text-accent ${className ?? ""}`}>
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          preserveAspectRatio="none"
          className="h-10 w-full"
          role="img"
          aria-label={`${prefix}: no data.`}
        >
          <line
            x1={0}
            y1={VIEW_H - PAD_Y}
            x2={VIEW_W}
            y2={VIEW_H - PAD_Y}
            stroke="currentColor"
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </span>
    );
  }

  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min;
  const step = n > 1 ? VIEW_W / (n - 1) : 0;

  const coords = points.map((value, i) => {
    const x = n > 1 ? i * step : VIEW_W / 2;
    return { x, y: projectY(value, min, range) };
  });

  const line = coords.map((c) => `${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(" ");
  // Close the area down to the baseline at each end so the fill sits under the line.
  const first = coords[0];
  const last = coords[coords.length - 1];
  const area = `${first.x.toFixed(2)},${VIEW_H} ${line} ${last.x.toFixed(2)},${VIEW_H}`;

  const ariaLabel =
    n === 1
      ? `${prefix}: single point at ${format(points[0])}.`
      : `${prefix} over ${n} points: starts at ${format(points[0])}, ends at ${format(
          points[n - 1]
        )}, ranging ${format(min)} to ${format(max)}.`;

  return (
    <span className={`block text-accent ${className ?? ""}`}>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        className="h-10 w-full"
        role="img"
        aria-label={ariaLabel}
      >
        <polygon points={area} fill="currentColor" className="opacity-10" />
        <polyline
          points={line}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </span>
  );
}
