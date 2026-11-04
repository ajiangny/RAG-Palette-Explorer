import { useEffect, useRef, useState } from 'react'
import { colorName, hexToOklch, isHex, normalizeHex, oklchToHex, type Oklch } from '../lib/color'
import { MAX_DOTS, shuffleHues } from '../lib/queryPalette'

type Props = {
  /** The dots shown. While the query is inactive these are the center painting's colors. */
  colors: string[]
  active: boolean
  onChange: (colors: string[]) => void
  onClear: () => void
  /** Null until the collection file has loaded. */
  onSurprise: (() => void) | null
  match: { title: string; onGrow: () => void } | null
}

export default function PaletteEditor({ colors, active, onChange, onClear, onSurprise, match }: Props) {
  const [open, setOpen] = useState<number | null>(null)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open === null) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(null) }
    const onDown = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(null) }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onDown)
    }
  }, [open])

  const replace = (i: number, hex: string) => onChange(colors.map((c, j) => (j === i ? hex : c)))
  const remove = (i: number) => {
    onChange(colors.filter((_, j) => j !== i))
    setOpen(null)
  }
  const add = () => {
    onChange([...colors, colors.length ? shuffleHues([colors[colors.length - 1]])[0] : '#8a7a60'])
    setOpen(colors.length)
  }

  return (
    <div ref={root} className="palette-editor" role="group" aria-label="Spotlight colors">
      {match && (
        <div className="editor-match">
          <span className="muted">Closest painting</span>
          <span className="editor-match-title" title={match.title}>{match.title}</span>
          <button className="secondary" onClick={match.onGrow}>Grow web from it</button>
        </div>
      )}
      {open !== null && colors[open] && (
        <ColorPopover key={open} hex={colors[open]} canDelete={colors.length > 1}
                      onChange={(hex) => replace(open, hex)} onDelete={() => remove(open)} />
      )}
      <div className="editor-row">
        <div className={`dots${active ? '' : ' inactive'}`}>
          {colors.map((hex, i) => (
            <button key={i} className={`dot${open === i ? ' open' : ''}`} style={{ background: hex }}
                    aria-label={`${colorName(hex)}, ${hex}. Edit color.`} aria-expanded={open === i}
                    title={hex} onClick={() => setOpen(open === i ? null : i)} />
          ))}
          {colors.length < MAX_DOTS && (
            <button className="dot add" aria-label="Add a color" title="Add a color" onClick={add}>+</button>
          )}
        </div>
        <button className="secondary" title="Rotate every hue by the same amount" onClick={() => onChange(shuffleHues(colors))}>Shuffle</button>
        <button className="secondary" disabled={!onSurprise} title="Try the palette of a painting in the collection"
                onClick={() => onSurprise?.()}>Surprise me</button>
        {active && <button className="link" onClick={() => { setOpen(null); onClear() }}>Clear</button>}
      </div>
    </div>
  )
}

function ColorPopover({ hex, canDelete, onChange, onDelete }: {
  hex: string
  canDelete: boolean
  onChange: (hex: string) => void
  onDelete: () => void
}) {
  // Held here because hex loses the hue of a gray and the chroma of an out-of-gamut request,
  // and sliders shouldn't jump when the color passes through either.
  const [color, setColor] = useState<Oklch>(() => hexToOklch(hex))
  const [draft, setDraft] = useState<string | null>(null)

  const set = (patch: Partial<Oklch>) => {
    const next = { ...color, ...patch }
    setColor(next)
    setDraft(null)
    onChange(oklchToHex(next))
  }

  return (
    <div className="color-popover">
      <Slider label="Lightness" value={color.l} max={1} step={0.005} onChange={(l) => set({ l })} />
      <Slider label="Chroma" value={color.c} max={0.37} step={0.002} onChange={(c) => set({ c })} />
      <Slider label="Hue" value={color.h} max={360} step={1} onChange={(h) => set({ h })} />
      <div className="popover-foot">
        <input aria-label="Hex color" spellCheck={false} value={draft ?? hex}
               onChange={(e) => {
                 const value = e.target.value.trim()
                 setDraft(value)
                 if (isHex(value)) {
                   const next = normalizeHex(value)
                   setColor(hexToOklch(next))
                   onChange(next)
                 }
               }}
               onBlur={() => setDraft(null)} />
        {canDelete && <button className="link" onClick={onDelete}>Remove</button>}
      </div>
    </div>
  )
}

function Slider({ label, value, max, step, onChange }: {
  label: string
  value: number
  max: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label className="slider">
      <span>{label}</span>
      <input type="range" min={0} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}
