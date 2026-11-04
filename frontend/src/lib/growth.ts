// The web's opening animation: a painting breaks into tiles snapped to its palette, and each new
// node assembles from palette-colored tiles that fly out of its parent, ring by ring.

import { hexToLab, rgbToLab, type Lab } from './color.ts'

export const TIMING = {
  /** The center dissolves into tiles, holds, then resolves back into the painting. */
  dissolve: 800,
  hold: 450,
  centerResolve: 450,
  /** When the first ring leaves the center, and the gap between rings. */
  firstRing: 850,
  ringGap: 620,
  /** A ring's nodes start within this window, however many there are. */
  ringSpread: 420,
  assemble: 620,
  resolve: 300,
} as const

export const CENTER_RADIUS = 34
const MIN_RADIUS = 9
const MAX_RADIUS = 22
const SELECTED_GROWTH = 0.22

/**
 * A node's drawn radius. Area follows `similarity` (0–1, to the center's palette), since eyes compare
 * circles by area. `selection` runs 0–1 as the node is selected. The center is always the largest.
 */
export function nodeRadius(isCenter: boolean, similarity: number, selection: number): number {
  const base = isCenter ? CENTER_RADIUS : Math.sqrt(MIN_RADIUS ** 2 + (MAX_RADIUS ** 2 - MIN_RADIUS ** 2) * similarity)
  return base * (1 + SELECTED_GROWTH * selection)
}

export const centerDuration = TIMING.dissolve + TIMING.hold + TIMING.centerResolve
const nodeDuration = TIMING.assemble + TIMING.resolve

type Id = number | string
export type Birth<T extends Id = Id> = { birth: number; parent: T | null }

/** The node a painting hangs from: its strongest link to something closer to the center, or already on the map. */
export function parentOf<T extends Id>(id: T, depth: ReadonlyMap<T, number>,
                                       edges: { source: T; target: T; score: number }[], center: T,
                                       known: ReadonlySet<T> = new Set()): T | null {
  let best: T | null = null
  let bestScore = -Infinity
  for (const e of edges) {
    const other = e.source === id ? e.target : e.target === id ? e.source : null
    if (other == null || e.score <= bestScore) continue
    const closerToCenter = (depth.get(other) ?? Infinity) < depth.get(id)!
    if (closerToCenter || (known.has(other) && !known.has(id))) {
      best = other
      bestScore = e.score
    }
  }
  return id === center ? null : best ?? center
}

/**
 * When each new node appears (ms from the start of this growth) and which node it flies out of.
 * `known` holds nodes already on the map; only new nodes get a plan, so expanding one painting
 * grows only its neighbors.
 */
export function planBirths<T extends Id>(nodes: { id: T; depth: number }[],
                                         edges: { source: T; target: T; score: number }[], center: T,
                                         known: ReadonlySet<T> = new Set()): Map<T, Birth<T>> {
  const depth = new Map(nodes.map((n) => [n.id, n.depth]))
  const fresh = nodes.filter((n) => !known.has(n.id))
  const plan = new Map<T, Birth<T>>()
  const startsAtCenter = fresh.some((n) => n.id === center)
  if (startsAtCenter) plan.set(center, { birth: 0, parent: null })

  const rings = [...new Set(fresh.filter((n) => n.id !== center).map((n) => n.depth))].sort((a, b) => a - b)
  rings.forEach((ringDepth, ring) => {
    const members = fresh.filter((n) => n.depth === ringDepth && n.id !== center)
    const step = Math.min(80, TIMING.ringSpread / members.length)
    const start = (startsAtCenter ? TIMING.firstRing : 0) + ring * TIMING.ringGap
    members.forEach((n, i) => plan.set(n.id, { birth: start + i * step, parent: parentOf(n.id, depth, edges, center, known) }))
  })
  return plan
}

/** When the last node has finished, in ms from the start of this growth. */
export function growthEnd(plan: Map<Id, Birth>): number {
  let end = 0
  for (const { birth, parent } of plan.values()) {
    end = Math.max(end, birth + (parent == null ? centerDuration : nodeDuration))
  }
  return end
}

export type Tile = {
  /** Position in the node's unit circle. */
  u: number
  v: number
  color: string
  /** 0–1: when this tile moves, within the node's animation. */
  delay: number
  /** A sideways drift while flying, so tiles travel as a swarm and not a line. */
  driftX: number
  driftY: number
}

const nearestSwatch = (lab: Lab, swatches: { lab: Lab; hex: string }[]) => {
  let best = swatches[0]
  let bestD = Infinity
  for (const s of swatches) {
    const d = (lab[0] - s.lab[0]) ** 2 + (lab[1] - s.lab[1]) ** 2 + (lab[2] - s.lab[2]) ** 2
    if (d < bestD) {
      best = s
      bestD = d
    }
  }
  return best.hex
}

/** Reads the image's colors at tile resolution. Returns null if the image can't be read. */
function sampleImage(img: HTMLImageElement, grid: number): Uint8ClampedArray | null {
  try {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = grid
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return null
    const side = Math.min(img.naturalWidth, img.naturalHeight)
    ctx.drawImage(img, (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side, 0, 0, grid, grid)
    return ctx.getImageData(0, 0, grid, grid).data
  } catch {
    return null // a cross-origin image without CORS headers taints the canvas
  }
}

/**
 * The node's disc as a grid of square tiles, each snapped to its nearest palette color.
 * Without a readable image, tiles are dealt in proportion to the palette's weights.
 */
export function buildTiles(img: HTMLImageElement | null, palette: { hex: string; weight: number }[], grid: number,
                           random = Math.random): Tile[] {
  const swatches = palette.map((s) => ({ hex: s.hex, lab: hexToLab(s.hex) }))
  const pixels = img?.complete && img.naturalWidth ? sampleImage(img, grid) : null
  const tiles: Tile[] = []
  for (let row = 0; row < grid; row++) {
    for (let col = 0; col < grid; col++) {
      const u = (col + 0.5) / grid * 2 - 1
      const v = (row + 0.5) / grid * 2 - 1
      const radius = Math.hypot(u, v)
      if (radius > 1) continue
      let color = ''
      if (pixels) {
        const i = (row * grid + col) * 4
        color = nearestSwatch(rgbToLab([pixels[i], pixels[i + 1], pixels[i + 2]]), swatches)
      } else {
        let pick = random()
        color = palette[palette.length - 1]?.hex ?? '#888888'
        for (const s of palette) {
          pick -= s.weight
          if (pick <= 0) {
            color = s.hex
            break
          }
        }
      }
      tiles.push({
        u, v, color,
        delay: Math.min(1, (1 - radius) * 0.6 + random() * 0.4),
        driftX: (random() - 0.5) * 2,
        driftY: (random() - 0.5) * 2,
      })
    }
  }
  return tiles
}

