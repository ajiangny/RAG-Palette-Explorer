// The whole collection's palettes, from the static file written by backend/ingest/export_palettes.py.

import { hexToLab, type Lab } from './color.ts'
import { MAX_DOTS } from './queryPalette.ts'
import { chamfer, type WeightedColor } from './spotlight.ts'

type RawItem = { id: number; t: string; c: string; w: number[] }
export type Painting = { id: number; title: string; hexes: string[]; palette: WeightedColor[] }

export function parseItems(items: RawItem[]): Painting[] {
  return items.map(({ id, t, c, w }) => {
    const hexes = w.map((_, i) => `#${c.slice(i * 6, i * 6 + 6)}`)
    return { id, title: t, hexes, palette: hexes.map((hex, i) => ({ lab: hexToLab(hex), weight: w[i] })) }
  })
}

/** The closest painting to the query, skipping `exclude` (usually the current center). */
export function bestMatch(paintings: Painting[], query: Lab[], exclude?: number | string | null): Painting | null {
  let best: Painting | null = null
  let bestScore = Infinity
  for (const p of paintings) {
    if (p.id === exclude) continue
    const score = chamfer(query, p.palette)
    if (score < bestScore) {
      best = p
      bestScore = score
    }
  }
  return best
}

/** Deals every painting once, in random order, so Surprise Me doesn't repeat until the deck runs out. */
export function makeDeck(paintings: Painting[], random = Math.random): () => string[] {
  const order = paintings.map((_, i) => i)
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[order[i], order[j]] = [order[j], order[i]]
  }
  let next = 0
  return () => {
    const dealt = paintings[order[next]]
    next = (next + 1) % order.length
    return dealt.hexes.slice(0, MAX_DOTS)
  }
}

let loaded: Promise<Painting[]> | null = null

export function loadCollection(): Promise<Painting[]> {
  loaded ??= fetch(`${import.meta.env.BASE_URL}palettes.json`)
    .then((res) => {
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json() as Promise<{ items: RawItem[] }>
    })
    .then(({ items }) => parseItems(items))
    .catch((e) => {
      loaded = null // a later attempt may succeed
      throw e
    })
  return loaded
}
