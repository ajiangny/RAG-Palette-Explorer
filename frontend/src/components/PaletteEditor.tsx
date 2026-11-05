import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { colorName, hexToHsv, hsvToHex, isHex, normalizeHex, type Hsv } from '../lib/color'
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
  const [menu, setMenu] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open === null && !menu) return
    const close = () => { setOpen(null); setMenu(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    const onDown = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) close() }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onDown)
    }
  }, [open, menu])

  const replace = (i: number, hex: string) => onChange(colors.map((c, j) => (j === i ? hex : c)))
  const remove = (i: number) => {
    onChange(colors.filter((_, j) => j !== i))
    setOpen(null)
  }
  const add = () => {
    onChange([...colors, colors.length ? shuffleHues([colors[colors.length - 1]])[0] : '#8a7a60'])
    setOpen(colors.length)
    setMenu(false)
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
      {menu && (
        <div className="editor-menu">
          {colors.length < MAX_DOTS && <button className="secondary" onClick={add}>Add color</button>}
          <button className="secondary" title="Rotate every hue by the same amount" onClick={() => onChange(shuffleHues(colors))}>Shuffle</button>
          <button className="secondary" disabled={!onSurprise} title="Try the palette of a painting in the collection"
                  onClick={() => onSurprise?.()}>Surprise me</button>
        </div>
      )}
      <div className="editor-row">
        <div className="dots">
          {colors.map((hex, i) => (
            <button key={i} className={`dot${open === i ? ' open' : ''}`} style={{ background: hex }}
                    aria-label={`${colorName(hex)}, ${hex}. Edit color.`} aria-expanded={open === i}
                    title={hex} onClick={() => { setMenu(false); setOpen(open === i ? null : i) }} />
          ))}
        </div>
        <button className="more" aria-label="More color options" aria-expanded={menu} title="More color options"
                onClick={() => { setOpen(null); setMenu(!menu) }}>⋯</button>
        {active && <button className="link" onClick={() => { setOpen(null); setMenu(false); onClear() }}>Clear</button>}
      </div>
    </div>
  )
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

/** Follows a pointer from press to release, reporting its position within the element as 0–1. */
function dragHandlers(onMove: (x: number, y: number) => void) {
  const report = (e: ReactPointerEvent<HTMLElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    onMove(clamp01((e.clientX - box.left) / box.width), clamp01((e.clientY - box.top) / box.height))
  }
  return {
    onPointerDown: (e: ReactPointerEvent<HTMLElement>) => {
      e.currentTarget.setPointerCapture(e.pointerId)
      report(e)
    },
    onPointerMove: (e: ReactPointerEvent<HTMLElement>) => {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) report(e)
    },
  }
}

/** The arrow-key step as [x, y], or null for any other key. Shift moves further. */
function arrowStep(e: ReactKeyEvent, size: number): [number, number] | null {
  const step = (e.shiftKey ? 10 : 1) * size
  const move = ({ ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] } as Record<string, [number, number]>)[e.key]
  return move ?? null
}

function ColorPopover({ hex, canDelete, onChange, onDelete }: {
  hex: string
  canDelete: boolean
  onChange: (hex: string) => void
  onDelete: () => void
}) {
  // Held here because hex loses the hue of a gray or a black, and the handles shouldn't jump there.
  const [color, setColor] = useState<Hsv>(() => hexToHsv(hex))
  const [draft, setDraft] = useState<string | null>(null)

  const set = (patch: Partial<Hsv>) => {
    const next = { ...color, ...patch }
    setColor(next)
    setDraft(null)
    onChange(hsvToHex(next))
  }
  const hue = hsvToHex({ h: color.h, s: 1, v: 1 })

  return (
    <div className="color-popover">
      <div className="hue-strip" {...dragHandlers((x) => set({ h: x * 360 }))}>
        <div className="hue-handle" role="slider" tabIndex={0} aria-label="Hue" aria-valuemin={0} aria-valuemax={360}
             aria-valuenow={Math.round(color.h)} style={{ left: `${(color.h / 360) * 100}%`, background: hue }}
             onKeyDown={(e) => {
               const step = arrowStep(e, 3)
               if (!step) return
               e.preventDefault()
               set({ h: Math.min(360, Math.max(0, color.h + step[0] + step[1])) })
             }} />
      </div>
      <div className="color-field" style={{ backgroundColor: hue }}
           {...dragHandlers((x, y) => set({ s: x, v: 1 - y }))}>
        <div className="field-handle" role="slider" tabIndex={0} aria-label="Color" aria-valuetext={colorName(hex)}
             aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(color.v * 100)}
             style={{ left: `${color.s * 100}%`, top: `${(1 - color.v) * 100}%`, background: hex }}
             onKeyDown={(e) => {
               const step = arrowStep(e, 0.02)
               if (!step) return
               e.preventDefault()
               set({ s: clamp01(color.s + step[0]), v: clamp01(color.v + step[1]) })
             }} />
      </div>
      <div className="popover-foot">
        <input aria-label="Hex color" spellCheck={false} value={draft ?? hex}
               onChange={(e) => {
                 const value = e.target.value.trim()
                 setDraft(value)
                 if (isHex(value)) {
                   const next = normalizeHex(value)
                   setColor(hexToHsv(next))
                   onChange(next)
                 }
               }}
               onBlur={() => setDraft(null)} />
        {canDelete && (
          <button className="icon" aria-label="Remove color" title="Remove color" onClick={onDelete}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8"
                 strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
