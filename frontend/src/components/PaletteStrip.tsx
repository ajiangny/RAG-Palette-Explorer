import type { Swatch } from '../api'

/** Proportional color bar: each swatch's width is its share of the image's pixels. */
export default function PaletteStrip({ palette }: { palette: Swatch[] }) {
  return (
    <div className="palette">
      {palette.map((s) => (
        <div key={s.hex} className="palette-swatch" style={{ background: s.hex, flexGrow: s.weight }}
             title={`${s.hex} · ${(s.weight * 100).toFixed(0)}%`} />
      ))}
    </div>
  )
}
