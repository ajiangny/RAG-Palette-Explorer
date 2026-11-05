// A tidy radial map: the center in the middle, each ring one step further out, and every node's
// children fanned out together in their own wedge, so a neighborhood stays visibly together.

import { parentOf } from './growth.ts'

type Id = number | string
export type Point = { x: number; y: number }
type LayoutNode<T> = { id: T; depth: number }
type LayoutEdge<T> = { source: T; target: T; score: number }

const FIRST_RING = 190
const RING_GAP = 150
const DEFAULT_SIZE = 20
/** Space between circles along a ring. Enough for one of them to grow when selected. */
const CIRCLE_GAP = 12
const MAX_PASSES = 6
const MAX_FITS = 6

/** Each ring's radius. Rings needing more length than they have move outward. */
function ringRadii<T>(nodes: LayoutNode<T>[], sizeOf: (id: T) => number, scale: number): number[] {
  const lengths: number[] = []
  for (const n of nodes) lengths[n.depth] = (lengths[n.depth] ?? 0) + 2 * sizeOf(n.id) + CIRCLE_GAP
  const radii = [0]
  for (let d = 1; d < lengths.length; d++) {
    const needed = (lengths[d] ?? 0) / (2 * Math.PI)
    radii[d] = Math.max((d === 1 ? FIRST_RING : radii[d - 1] + RING_GAP) * scale, needed)
  }
  return radii
}

/**
 * Target positions for every node. The same graph always gives the same layout.
 * `sizeOf` gives a node's radius, and a larger circle gets a wider share of its ring.
 */
export function radialLayout<T extends Id>(nodes: LayoutNode<T>[], edges: LayoutEdge<T>[], center: T,
                                           sizeOf: (id: T) => number = () => DEFAULT_SIZE): Map<T, Point> {
  const depth = new Map(nodes.map((n) => [n.id, n.depth]))
  const children = new Map<T, T[]>(nodes.map((n) => [n.id, []]))
  for (const n of nodes) {
    if (n.id !== center) children.get(parentOf(n.id, depth, edges, center) ?? center)?.push(n.id)
  }

  // The angle each node's wedge needs: room for itself, or for everything beneath it if that's more.
  let radii: number[] = []
  const wedge = new Map<T, number>()
  const measure = (id: T): number => {
    const own = id === center ? 0 : (2 * sizeOf(id) + CIRCLE_GAP) / radii[depth.get(id)!]
    const total = Math.max(own, children.get(id)!.reduce((sum, k) => sum + measure(k), 0))
    wedge.set(id, total)
    return total
  }
  // A branch's wedge can be wider than its nodes need, so push the rings out until all of them fit.
  for (let fit = 0, scale = 1; fit < MAX_FITS; fit++) {
    radii = ringRadii(nodes, sizeOf, scale)
    const needed = measure(center)
    if (needed <= 2 * Math.PI) break
    scale *= needed / (2 * Math.PI)
  }

  const place = () => {
    const out = new Map<T, Point>()
    const visit = (id: T, from: number, to: number) => {
      const angle = (from + to) / 2
      const r = radii[depth.get(id)!] ?? 0
      out.set(id, { x: r * Math.cos(angle), y: r * Math.sin(angle) })
      const kids = children.get(id)!
      const shared = kids.reduce((sum, k) => sum + wedge.get(k)!, 0)
      let start = from
      for (const kid of kids) {
        const share = (to - from) * wedge.get(kid)! / shared
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

/** The screen-pixel shift that brings a point out from under an overlay; zero if it's already clear. */
export function panToReveal(
  point: Point,
  box: { width: number; height: number },
  cover: { right: number; bottom: number },
  margin: number,
): Point {
  const maxX = box.width - cover.right - margin
  const maxY = box.height - cover.bottom - margin
  return { x: point.x > maxX ? maxX - point.x : 0, y: point.y > maxY ? maxY - point.y : 0 }
}
