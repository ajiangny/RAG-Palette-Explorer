// How well a painting's palette answers the user's colors.

import type { Lab } from './color.ts'

export type WeightedColor = { lab: Lab | number[]; weight: number }

const distance = (a: ArrayLike<number>, b: ArrayLike<number>) =>
  Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

function nearest(lab: ArrayLike<number>, palette: WeightedColor[]): number {
  let best = Infinity
  for (const p of palette) best = Math.min(best, distance(lab, p.lab))
  return best
}

/** One or two dots ask "does it contain these colors?"; five ask "does its palette resemble mine?" */
export const lambdaFor = (dots: number) => (Math.min(dots, 5) - 1) / 4

/**
 * Weighted Chamfer distance in CIELAB (lower is closer). Cheap enough to run on every pointer move.
 * Exact EMD reranking comes later, in the server stage.
 */
export function chamfer(query: Lab[], palette: WeightedColor[], lambda = lambdaFor(query.length)): number {
  if (!query.length || !palette.length) return Infinity
  let toPalette = 0
  for (const q of query) toPalette += nearest(q, palette) / query.length
  let toQuery = 0
  const asQuery = query.map((lab) => ({ lab, weight: 1 }))
  for (const p of palette) toQuery += p.weight * nearest(p.lab, asQuery)
  return (toPalette + lambda * toQuery) / (1 + lambda)
}

/** How far apart two palettes are, each color counted by its share of the painting. Lower is closer. */
export function paletteDistance(a: WeightedColor[], b: WeightedColor[]): number {
  if (!a.length || !b.length) return Infinity
  let total = 0
  for (const p of a) total += p.weight * nearest(p.lab, b)
  for (const q of b) total += q.weight * nearest(q.lab, a)
  return total / 2
}

/**
 * Each painting's similarity to the center's palette, from 0 (the least similar in this web) to 1 (the most).
 * Scaled by the actual distances, so two near-equal paintings get near-equal values.
 */
export function similarityToCenter<T>(nodes: { id: T; palette: WeightedColor[] }[], center: T): Map<T, number> {
  const anchor = nodes.find((n) => n.id === center)?.palette ?? []
  const distances = nodes.filter((n) => n.id !== center).map((n) => [n.id, paletteDistance(anchor, n.palette)] as const)
  const finite = distances.map(([, d]) => d).filter(Number.isFinite)
  const lo = Math.min(...finite)
  const hi = Math.max(...finite)
  const out = new Map<T, number>([[center, 1]])
  for (const [id, d] of distances) {
    out.set(id, !Number.isFinite(d) ? 0 : hi - lo < 1e-6 ? 0.5 : 1 - (d - lo) / (hi - lo))
  }
  return out
}

/**
 * 0–1 emphasis within this web, 1 being the closest. Based on rank rather than raw score, so one
 * near-perfect match (often the center itself) doesn't push every other painting to zero.
 */
export function emphasize<T>(scores: Map<T, number>): Map<T, number> {
  const ranked = [...scores].filter(([, s]) => Number.isFinite(s)).sort((a, b) => a[1] - b[1])
  const flat = ranked.length > 0 && ranked[ranked.length - 1][1] - ranked[0][1] < 1
  const out = new Map<T, number>()
  for (const id of scores.keys()) out.set(id, 0)
  ranked.forEach(([id], i) => {
    const closeness = flat || ranked.length === 1 ? 1 : 1 - i / (ranked.length - 1)
    out.set(id, closeness ** 2)
  })
  return out
}

/** The paintings to frame after the dots settle: the strong matches, and always at least `min`. */
export function framedIds<T>(emphasis: Map<T, number>, threshold: number, min: number): Set<T> {
  const ranked = [...emphasis].sort((a, b) => b[1] - a[1])
  return new Set(ranked.filter(([, e], i) => e > threshold || i < min).map(([id]) => id))
}
