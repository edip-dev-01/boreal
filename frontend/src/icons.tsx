import type { CSSProperties } from 'react'
import { PRODUCT_NAME } from './config'
const paths = {
  search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></>,
  pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2.3"/></>,
  layers: <><path d="m12 3 10 5-10 5L2 8l10-5Zm-9 10 9 5 9-5M3 18l9 5 9-5"/></>,
  arrow: <><path d="M5 12h14m-5-5 5 5-5 5"/></>,
  close: <path d="m6 6 12 12M6 18 18 6"/>,
  chevron: <path d="m9 5 7 7-7 7"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
  spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/></>,
  link: <><path d="m10 14 4-4m-6 6-2 2a4.2 4.2 0 0 1-6-6l4-4a4.2 4.2 0 0 1 6 0m4 0 2-2a4.2 4.2 0 0 1 6 6l-4 4a4.2 4.2 0 0 1-6 0" transform="translate(1 0) scale(.92)"/></>,
  alert: <><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3v.2"/></>,
  target: <><rect x="5" y="5" width="14" height="14" rx="2"/><path d="M12 2v6m0 8v6M2 12h6m8 0h6"/></>,
  logout: <><path d="M10 4H4v16h6m4-13 5 5-5 5m-6-5h12"/></>,
  table: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M9 4v16"/></>,
  globe: <><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/></>,
  check: <path d="m5 12 4 4 10-10"/>,
} as const
export type IconName = keyof typeof paths
export function Icon({ name, size = 18, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" style={style}>{paths[name]}</svg>
}
export function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? 'brand-small' : ''}`}><span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M8 26V6h8c9 0 9 9 1 10 11 0 11 10 0 10H8m0-10h9" stroke="currentColor" strokeWidth="2.5"/><circle cx="16" cy="5" r="1.8" fill="currentColor"/></svg></span><span>{PRODUCT_NAME}<span className="brand-dot">.</span></span></div>
}
