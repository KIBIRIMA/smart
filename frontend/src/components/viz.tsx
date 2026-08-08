"use client";
import { C } from "@/lib/theme";

// Dataviz Power BI — SVG natif, zéro dépendance.
// Donut · Gauge · Bars · Lines · Legend. À utiliser librement dans les pages.

export const Donut = ({
  value, size = 100, stroke = 12, color = C.brand, center, sub, label,
}: {
  value: number; size?: number; stroke?: number; color?: string;
  center?: string; sub?: string; label?: string;
}) => {
  const r = (size - stroke) / 2, cx = size / 2, circ = 2 * Math.PI * r;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size}>
          <circle cx={cx} cy={cx} r={r} fill="none" stroke={C.track} strokeWidth={stroke} />
          <circle cx={cx} cy={cx} r={r} fill="none" stroke={color} strokeWidth={stroke}
            strokeDasharray={circ} strokeDashoffset={circ * (1 - value / 100)}
            strokeLinecap="round" transform={`rotate(-90 ${cx} ${cx})`} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: size > 84 ? 20 : 15, fontWeight: 800, color: C.brand, lineHeight: 1 }}>
              {center ?? `${value}%`}</div>
            {sub && <div style={{ fontSize: 9, color: C.textFaint, marginTop: 2 }}>{sub}</div>}
          </div>
        </div>
      </div>
      {label && <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".05em",
        textTransform: "uppercase", color: C.textFaint }}>{label}</div>}
    </div>
  );
};

export const Gauge = ({
  value, max = 100, color = C.brand, unit = "%",
}: { value: number; max?: number; color?: string; unit?: string }) => {
  const w = 140, h = 84, cx = w / 2, cy = h - 6, r = 56, stroke = 12;
  const pol = (a: number): [number, number] => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const arc = (a0: number, a1: number) => {
    const [x0, y0] = pol(a0), [x1, y1] = pol(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`;
  };
  const frac = Math.min(value / max, 1);
  return (
    <svg width={w} height={h}>
      <path d={arc(Math.PI, 2 * Math.PI)} fill="none" stroke={C.track} strokeWidth={stroke} strokeLinecap="round" />
      <path d={arc(Math.PI, Math.PI + Math.PI * frac)} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" />
      <text x={cx} y={cy - 11} textAnchor="middle" fontSize="20" fontWeight="800" fill={C.brand} fontFamily={C.font}>
        {value}<tspan fontSize="11">{unit}</tspan></text>
    </svg>
  );
};

export const Bars = ({
  data, colors, labels,
}: { data: number[][]; colors: string[]; labels: string[] }) => {
  const w = 300, h = 130, pad = 22, gap = 26;
  const max = Math.max(...data.flat()) * 1.15;
  const groupW = (w - pad * 2 - gap * (data.length - 1)) / data.length;
  const barW = groupW / colors.length - 3;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`}>
      {[0, .5, 1].map((t, i) => (
        <line key={i} x1={pad} x2={w - pad} y1={pad + (h - pad * 2) * t} y2={pad + (h - pad * 2) * t} stroke={C.track} strokeWidth="1" />
      ))}
      {data.map((grp, gi) => {
        const gx = pad + gi * (groupW + gap);
        return (
          <g key={gi}>
            {grp.map((v, si) => {
              const bh = (v / max) * (h - pad * 2);
              return <rect key={si} x={gx + si * (barW + 3)} y={h - pad - bh} width={barW} height={bh} rx="2" fill={colors[si]} />;
            })}
            <text x={gx + groupW / 2} y={h - 6} textAnchor="middle" fontSize="9" fill={C.textMut} fontFamily={C.font}>{labels[gi]}</text>
          </g>
        );
      })}
    </svg>
  );
};

export const Lines = ({
  series, colors, xlabels,
}: { series: number[][]; colors: string[]; xlabels: string[] }) => {
  const w = 300, h = 130, pad = 24;
  const max = Math.max(...series.flat()) * 1.1;
  const n = series[0].length;
  const px = (i: number) => pad + (w - pad * 2) * (i / (n - 1));
  const py = (v: number) => h - pad - (h - pad * 2) * (v / max);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`}>
      {[0, .5, 1].map((t, i) => (
        <line key={i} x1={pad} x2={w - pad} y1={pad + (h - pad * 2) * t} y2={pad + (h - pad * 2) * t} stroke={C.track} strokeWidth="1" />
      ))}
      {series.map((s, si) => (
        <polyline key={si} fill="none" stroke={colors[si]} strokeWidth="2.5" strokeLinejoin="round"
          strokeLinecap="round" points={s.map((v, i) => `${px(i)},${py(v)}`).join(" ")} />
      ))}
      {series.map((s, si) => s.map((v, i) => (
        <circle key={`${si}-${i}`} cx={px(i)} cy={py(v)} r="2.5" fill={colors[si]} />
      )))}
      {xlabels.map((l, i) => (
        <text key={i} x={px(i)} y={h - 6} textAnchor="middle" fontSize="8" fill={C.textMut} fontFamily={C.font}>{l}</text>
      ))}
    </svg>
  );
};

export const Legend = ({ items }: { items: [string, string][] }) => (
  <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8 }}>
    {items.map(([c, l]) => (
      <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: C.textMut }}>
        <span style={{ width: 9, height: 9, borderRadius: 2, background: c }} />{l}
      </span>
    ))}
  </div>
);
