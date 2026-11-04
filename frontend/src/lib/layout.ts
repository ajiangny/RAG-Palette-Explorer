// A tidy radial map: the center in the middle, each ring one step further out, and every node's
// children fanned out together in their own wedge, so a neighborhood stays visibly together.

import { parentOf } from './growth.ts'

type Id = number | string
export type Point = { x: number; y: number }
type LayoutNode<T> = { id: T; depth: number }
type LayoutEdge<T> = { source: T; target: T; score: number }

const FIRST_RING = 150
const RING_GAP = 135
/** Room along a ring per node, by depth. Crowded rings move outward to keep it. */
const SPACING = [0, 62, 52, 52]
const MAX_PASSES = 6

function ringRadii<T>(nodes: LayoutNode<T>[]): number[] {
  const counts: number[] = []
  for (const n of nodes) counts[n.depth] = (counts[n.depth] ?? 0) + 1
  const radii = [0]
  for (let d = 1; d < counts.length; d++) {
    const spacing = SPACING[Math.min(d, SPACING.length - 1)]
    const needed = (counts[d] ?? 0) * spacing / (2 * Math.PI)
    radii[d] = Math.max(d === 1 ? FIRST_RING : radii[d - 1] + RING_GAP, needed)
  }
  return radii
}

/** Target positions for every node. The same graph always gives the same layout. */
export function radialLayout<T extends Id>(nodes: LayoutNode<T>[], edges: LayoutEdge<T>[], center: T): Map<T, Point> {
  const depth = new Map(nodes.map((n) => [n.id, n.depth]))
  const children = new Map<T, T[]>(nodes.map((n) => [n.id, []]))
  for (const n of nodes) {
    if (n.id !== center) children.get(parentOf(n.id, depth, edges, center) ?? center)?.push(n.id)
  }

  const radii = ringRadii(nodes)
  const leaves = new Map<T, number>()
  const countLeaves = (id: T): number => {
    const kids = children.get(id)!
    const total = kids.length ? kids.reduce((sum, k) => sum + countLeaves(k), 0) : 1
    leaves.set(id, total)
    return total
  }
  countLeaves(center)

  const place = () => {
    const out = new Map<T, Point>()
    const visit = (id: T, from: number, to: number) => {
      const angle = (from + to) / 2
      const r = radii[depth.get(id)!] ?? 0
      out.set(id, { x: r * Math.cos(angle), y: r * Math.sin(angle) })
      let start = from
      for (const kid of children.get(id)!) {
        const share = (to - from) * leaves.get(kid)! / leaves.get(id)!
        visit(kid, start, start + share)
        start += share
      }
    }
    visit(center, -Math.PI / 2, 1.5 * Math.PI)
    return out
  }

  // Shorter links cross less. Swap neighboring siblings for as long as that shortens the total.
  const cost = (at: Map<T, Point>) => edges.reduce((sum, e) => {
    const a = at.get(e.source)
    const b = at.get(e.target)
    return a && b ? sum + Math.hypot(a.x - b.x, a.y - b.y) : sum
  }, 0)
  let best = cost(place())
  for (let pass = 0; pass < MAX_PASSES; pass++) {
    let improved = false
    for (const kids of children.values()) {
      for (let i = 0; i + 1 < kids.length; i++) {
        ;[kids[i], kids[i + 1]] = [kids[i + 1], kids[i]]
        const next = cost(place())
        if (next < best - 1e-6) {
          best = next
          improved = true
        } else {
          ;[kids[i], kids[i + 1]] = [kids[i + 1], kids[i]]
        }
      }
    }
    if (!improved) break
  }
  return place()
}
