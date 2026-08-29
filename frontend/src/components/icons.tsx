import type { SVGProps } from "react";

/** Small line icons for the stat tiles - hand-drawn to match the app's own
 * mark spec (2px stroke, round joins) rather than pulling in an icon
 * library for five glyphs. Each renders in `currentColor` so the caller
 * sets color, not the icon. Purely decorative identity, never data - so
 * every usage pairs one with its metric's name (never color/icon alone). */
function baseProps(props: SVGProps<SVGSVGElement>): SVGProps<SVGSVGElement> {
  return {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    ...props,
  };
}

export function BatteryIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <rect x="2" y="7" width="17" height="10" rx="2" />
      <line x1="22" y1="10.5" x2="22" y2="13.5" />
      <line x1="6" y1="10" x2="6" y2="14" />
      <line x1="10" y1="10" x2="10" y2="14" />
    </svg>
  );
}

export function GaugeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 15a8 8 0 0 1 16 0" />
      <line x1="12" y1="15" x2="16" y2="10" />
      <line x1="4" y1="19" x2="4" y2="17" />
      <line x1="20" y1="19" x2="20" y2="17" />
    </svg>
  );
}

export function MoonIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M20 14.5A8 8 0 1 1 10 4a6.5 6.5 0 0 0 10 10.5z" />
    </svg>
  );
}

export function HeartPulseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M12 20 4.5 12.7a4.4 4.4 0 0 1 0-6.2 4.2 4.2 0 0 1 6 0l1.5 1.5 1.5-1.5a4.2 4.2 0 0 1 6 0 4.4 4.4 0 0 1 0 6.2z" />
      <polyline points="6,11.5 9,11.5 10.5,8.5 13,15 14.5,11.5 18,11.5" />
    </svg>
  );
}

export function WaveIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <polyline points="2,12 6,12 9,5 13,19 16,12 22,12" />
    </svg>
  );
}
