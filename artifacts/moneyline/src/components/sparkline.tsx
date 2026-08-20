/** Tiny SVG win-distribution sparkline for the Season Desk table. */
export function DistributionSparkline({
  distribution,
  width = 96,
  height = 22,
}: {
  distribution: { wins: number; count: number }[];
  width?: number;
  height?: number;
}) {
  if (!distribution?.length) return <span className="text-muted-foreground">—</span>;
  const max = Math.max(...distribution.map((d) => d.count));
  const barWidth = width / distribution.length;
  const lo = distribution[0].wins;
  const hi = distribution[distribution.length - 1].wins;

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label={`Simulated win distribution ${lo}–${hi}`}
      className="block"
    >
      {distribution.map((d, i) => {
        const h = max > 0 ? Math.max(1, (d.count / max) * (height - 2)) : 1;
        return (
          <rect
            key={d.wins}
            x={i * barWidth}
            y={height - h}
            width={Math.max(1, barWidth - 0.5)}
            height={h}
            className="fill-primary/70"
          >
            <title>{`${d.wins} W × ${d.count}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}
