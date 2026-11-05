import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d'
import { imageSrc, type Graph, type GraphNode, type NodeId } from '../api'
import { buildTiles, CENTER_RADIUS, centerDuration, growthEnd, nodeRadius, planBirths, TIMING, type Birth, type SizeTier, type Tile } from '../lib/growth'
import { panToReveal, radialLayout } from '../lib/layout'
import { chamfer, closestIds, emphasize, framedIds, similarityToCenter } from '../lib/spotlight'
import { hexToLab, paletteBands } from '../lib/color'
import { drawDissolve, makeDissolveSprite, type DissolveSprite } from '../lib/dissolveText'

type Node = NodeObject<GraphNode & {
  img?: string
  /** ms on the growth clock when this node appears, and the node it flies out of. */
  birth?: number
  parent?: NodeId | null
  tiles?: Tile[]
  tilesFromImage?: boolean
  /** 0–1: how close this palette is to the center's, within this web. Drives the node's size. */
  similarity?: number
  tier?: SizeTier
  /** Where the layout wants this node. */
  targetX?: number
  targetY?: number
  /** 0–1: how far this node has eased into its selected state, and when that last updated. */
  selection?: number
  selectionAt?: number
}>
type Link = LinkObject<Node, { score: number }>

export type EdgeRef = { source: NodeId; target: NodeId }
export type MapView = 'paintings' | 'pixels' | 'blocks'

type Props = {
  graph: Graph
  /** Changes when `graph` is a new web, as opposed to the current one with more nodes. */
  generation: number
  uploadPreview: string | null
  selectedNode: NodeId | null
  selectedEdge: EdgeRef | null
  /** The user's colors. Nodes dim by how poorly they match; null means no Spotlight. */
  query: string[] | null
  /** How paintings are drawn. Anything but `paintings` also picks out the closest palettes. */
  view: MapView
  /** The part of the map hidden by the details panel, in pixels from each edge. */
  cover: { right: number; bottom: number }
  onNodeClick: (id: NodeId) => void
  onEdgeClick: (edge: EdgeRef) => void
  onBackgroundClick: () => void
}

const TILE_GRID: Record<SizeTier, number> = { center: 36, closest: 16, other: 11 } // tiles across a node
const SELECTION_MS = 110 // time constant for easing into and out of selection
const LAYOUT_PULL = 0.35 // how firmly nodes return to the layout after a drag or an expansion
const COLORS = { background: '#161412', edge: [232, 224, 210], edgeActive: '#e8c66a', ring: '#e8c66a', label: '#f2ece2' }
const EDGE_ALPHA = 0.22
const REST_ALPHA = 0.3 // paintings outside the closest palettes, in the color views
const DIM_ALPHA = 0.1
const SETTLE_MS = 350
const FIT_PADDING = 72 // clears the controls floating over the map
const REVEAL_MARGIN = 120 // leaves room for half of a long title
const REVEAL_MS = 300
const FIT_MS = 600
const LABEL_FONT = "'Iowan Old Style', Palatino, Georgia, serif"
const CENTER_RING = 'rgba(242, 236, 226, 0.7)'
const EDGE_QUESTION = 'What\u2019s the connection?'
const QUESTION_IN_MS = 650
const QUESTION_OUT_MS = 380
const SELECTED_MIN_ALPHA = 0.55 // a selected node stays findable, without looking like a match
const MATCH_THRESHOLD = 0.5
const MIN_FRAMED = 6

/** A d3 force that eases each node to its layout position. */
function layoutForce() {
  let nodes: Node[] = []
  const force = (alpha: number) => {
    for (const n of nodes) {
      n.vx = (n.vx ?? 0) + ((n.targetX ?? 0) - n.x!) * LAYOUT_PULL * alpha
      n.vy = (n.vy ?? 0) + ((n.targetY ?? 0) - n.y!) * LAYOUT_PULL * alpha
    }
  }
  force.initialize = (next: Node[]) => { nodes = next }
  return force
}

const idOf = (end: Link['source']): NodeId => (typeof end === 'object' ? (end as Node).id as NodeId : end as NodeId)
const DONE = -1e9 // a clock origin so far back that every node has finished
const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const duration = (ms: number) => (prefersReducedMotion() ? 0 : ms)
const ease = (t: number) => 1 - (1 - t) ** 3
const clamp01 = (t: number) => Math.min(1, Math.max(0, t))

// One <img> per URL, shared across renders; the canvas redraws continuously so late loads show up.
// CORS mode lets the growth animation read pixels from a backend on another origin.
const imageCache = new Map<string, HTMLImageElement>()
function getImage(src: string): HTMLImageElement {
  let img = imageCache.get(src)
  if (!img) {
    img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = src
    imageCache.set(src, img)
  }
  return img
}

function drawPalettePie(ctx: CanvasRenderingContext2D, node: Node, r: number) {
  let angle = -Math.PI / 2
  for (const s of node.palette) {
    const next = angle + s.weight * 2 * Math.PI
    ctx.beginPath()
    ctx.moveTo(node.x!, node.y!)
    ctx.arc(node.x!, node.y!, r, angle, next)
    ctx.fillStyle = s.hex
    ctx.fill()
    angle = next
  }
}

/** The palette as solid bands, clipped to the circle. */
function drawBlocks(ctx: CanvasRenderingContext2D, node: Node, r: number) {
  ctx.save()
  ctx.beginPath()
  ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
  ctx.clip()
  for (const band of paletteBands(node.palette)) {
    ctx.fillStyle = band.hex
    // A hair of overlap, so the background doesn't show through the seams.
    ctx.fillRect(node.x! - r, node.y! - r + band.from * 2 * r, 2 * r, (band.to - band.from) * 2 * r + 0.5)
  }
  ctx.restore()
}

/** The painting as a mosaic of its own palette colors, as in the growth animation. */
function drawPixels(ctx: CanvasRenderingContext2D, node: Node, r: number) {
  const size = tileSize(node, r) * 1.04
  for (const t of tilesOf(node)) {
    ctx.fillStyle = t.color
    ctx.fillRect(node.x! + t.u * r - size / 2, node.y! + t.v * r - size / 2, size, size)
  }
}

function drawDisc(ctx: CanvasRenderingContext2D, node: Node, r: number, view: MapView) {
  if (view === 'blocks' && node.palette.length) {
    drawBlocks(ctx, node, r)
    return
  }
  if (view === 'pixels') {
    drawPixels(ctx, node, r)
    return
  }
  const img = node.img ? getImage(node.img) : null
  ctx.save()
  ctx.beginPath()
  ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
  ctx.clip()
  if (img?.complete && img.naturalWidth) {
    // Cover-fit the thumbnail into the circle.
    const k = (2 * r) / Math.min(img.naturalWidth, img.naturalHeight)
    const w = img.naturalWidth * k
    const h = img.naturalHeight * k
    ctx.drawImage(img, node.x! - w / 2, node.y! - h / 2, w, h)
  } else {
    drawPalettePie(ctx, node, r)
  }
  ctx.restore()
}

function tilesOf(node: Node): Tile[] {
  const img = node.img ? getImage(node.img) : null
  const loaded = !!img?.complete && img.naturalWidth > 0
  // Tiles made before the image arrived are only random palette colors, so redo them once it has.
  if (!node.tiles || (loaded && !node.tilesFromImage)) {
    node.tiles = buildTiles(img, node.palette, TILE_GRID[node.tier ?? 'other'])
    node.tilesFromImage = loaded
  }
  return node.tiles
}

const tileSize = (node: Node, r: number) => (2 * r) / TILE_GRID[node.tier ?? 'other']

/** The center: the painting's tiles snap to palette colors from the outside in, then it resolves back. */
function drawCenterGrowth(ctx: CanvasRenderingContext2D, node: Node, r: number, age: number, view: MapView) {
  const tiles = tilesOf(node)
  const size = tileSize(node, r) * 1.04
  const shown = clamp01(age / TIMING.dissolve)
  const resolving = clamp01((age - TIMING.dissolve - TIMING.hold) / TIMING.centerResolve)
  drawDisc(ctx, node, r, view)
  ctx.save()
  ctx.globalAlpha *= 1 - resolving
  for (const t of tiles) {
    if (t.delay > shown) continue
    ctx.fillStyle = t.color
    ctx.fillRect(node.x! + t.u * r - size / 2, node.y! + t.v * r - size / 2, size, size)
  }
  ctx.restore()
}

/** A new node: palette tiles swarm out of its parent, settle into a disc, then become the thumbnail. */
function drawNodeGrowth(ctx: CanvasRenderingContext2D, node: Node, parent: Node | undefined, r: number, age: number, view: MapView) {
  const tiles = tilesOf(node)
  const size = tileSize(node, r) * 1.04
  const from = parent ?? node
  const dx = node.x! - from.x!
  const dy = node.y! - from.y!
  const spread = Math.hypot(dx, dy) * 0.22
  const resolving = clamp01((age - TIMING.assemble) / TIMING.resolve)
  if (resolving > 0) {
    ctx.save()
    ctx.globalAlpha *= resolving
    drawDisc(ctx, node, r, view)
    ctx.restore()
  }
  ctx.save()
  ctx.globalAlpha *= 1 - resolving
  for (const t of tiles) {
    // Outer tiles leave first; each takes the same flight time.
    const flight = clamp01((age / TIMING.assemble - t.delay * 0.45) / 0.55)
    if (flight <= 0) continue
    const p = ease(flight)
    const bow = Math.sin(p * Math.PI) * spread
    const s = size * (0.55 + 0.45 * p)
    const x = from.x! + (dx + t.u * r) * p + t.driftX * bow
    const y = from.y! + (dy + t.v * r) * p + t.driftY * bow
    ctx.fillStyle = t.color
    ctx.fillRect(x - s / 2, y - s / 2, s, s)
  }
  ctx.restore()
}

export default function GraphView(props: Props) {
  const { graph, generation, uploadPreview, selectedNode, selectedEdge, query, view, cover } = props
  const fgRef = useRef<ForceGraphMethods<Node, Link> | undefined>(undefined)
  const boxRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 800, height: 600 })
  const [growing, setGrowing] = useState(false)
  const fitted = useRef(false)
  const engineStopped = useRef(false)
  const previous = useRef<{ generation: number; nodes: Map<NodeId, Node> } | null>(null)
  const clock = useRef<{ origin: number | null; end: number }>({ origin: null, end: 0 })
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  const sizeRef = useRef(size)
  sizeRef.current = size

  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ width: e.contentRect.width, height: e.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // The force engine mutates node/link objects, so hand it fresh copies per graph. When the web only
  // gained nodes, existing paintings keep their places and just the new ones grow.
  const data = useMemo(() => {
    const prior = previous.current?.generation === generation ? previous.current.nodes : null
    const plan: Map<NodeId, Birth<NodeId>> = prefersReducedMotion()
      ? new Map()
      : planBirths<NodeId>(graph.nodes, graph.edges, graph.center, new Set(prior?.keys() ?? []))
    const origin = prior ? clock.current.origin : null
    const start = origin != null ? performance.now() - origin : 0
    const similarity = similarityToCenter<NodeId>(graph.nodes, graph.center)
    const closest = closestIds(similarity, graph.center)
    const tierOf = (id: NodeId): SizeTier => (id === graph.center ? 'center' : closest.has(id) ? 'closest' : 'other')
    const layout = radialLayout<NodeId>(graph.nodes, graph.edges, graph.center,
      (id) => nodeRadius(tierOf(id), similarity.get(id) ?? 0, 0))
    const nodes: Node[] = graph.nodes.map((n) => {
      const before = prior?.get(n.id)
      const target = layout.get(n.id)!
      const birth = plan.get(n.id)
      const parent = birth?.parent != null ? prior?.get(birth.parent) : null
      const node: Node = {
        ...n,
        img: n.id === 'upload' ? uploadPreview ?? undefined : n.image_id && imageSrc(n.image_id),
        ...(n.id === graph.center ? { fx: 0, fy: 0 } : {}),
        similarity: similarity.get(n.id) ?? 0,
        tier: tierOf(n.id),
        targetX: target.x,
        targetY: target.y,
        // A new web starts in place, so nodes grow where they will stay.
        x: target.x,
        y: target.y,
        ...(before ? {
          x: before.x, y: before.y, vx: before.vx, vy: before.vy,
          birth: before.birth, parent: before.parent, selection: before.selection,
        } : {}),
        // Spawn on the expanded painting so new nodes push outward from it.
        ...(!before && parent ? { x: parent.x! + Math.random() - 0.5, y: parent.y! + Math.random() - 0.5 } : {}),
        ...(birth ? { birth: start + birth.birth, parent: birth.parent } : {}),
      }
      if (node.img) getImage(node.img) // start loading before the node is due
      return node
    })
    const links: Link[] = graph.edges.map((e) => ({ source: e.source, target: e.target, score: e.score }))
    return { nodes, links, origin, end: start + growthEnd(plan), fresh: !prior && plan.size > 0, animated: plan.size > 0 }
  }, [graph, generation, uploadPreview])

  // Before paint and before the canvas's next frame, so new nodes never flash on the old clock.
  useLayoutEffect(() => {
    clock.current = { origin: data.origin, end: data.end }
    previous.current = { generation, nodes: new Map(data.nodes.map((n) => [n.id as NodeId, n])) }
  }, [data, generation])

  const nodeById = useMemo(() => new Map(data.nodes.map((n) => [n.id as NodeId, n])), [data])

  // Edge scores rescaled to 0–1 within this web, for width and length.
  const norm = useMemo(() => {
    const scores = graph.edges.map((e) => e.score)
    const [lo, hi] = [Math.min(...scores), Math.max(...scores)]
    return (s: number) => (hi > lo ? (s - lo) / (hi - lo) : 1)
  }, [graph])
  const edgeWidth = (score: number) => 0.6 + 3 * norm(score) ** 2

  // Spotlight: how strongly each node answers the query. Rescored on every edit, without a network call.
  const emphasis = useMemo(() => {
    if (!query?.length) return null
    const labs = query.map(hexToLab)
    return emphasize(new Map(graph.nodes.map((n) => [n.id, chamfer(labs, n.palette)])))
  }, [query, graph])
  const emphasisOf = (id: NodeId) => (emphasis ? emphasis.get(id) ?? 0 : 1)

  // Bring the selected painting or line out from under the panel. The camera otherwise stays still.
  const reveal = useRef(() => {})
  const refitOnClose = useRef(false)
  useLayoutEffect(() => {
    reveal.current = () => {
      const fg = fgRef.current
      if (!fg) return
      const a = nodeById.get(selectedEdge ? selectedEdge.source : selectedNode as NodeId)
      const b = selectedEdge ? nodeById.get(selectedEdge.target) : a
      if (a?.x == null || b?.x == null) return
      const point = fg.graph2ScreenCoords((a.x + b.x) / 2, (a.y! + b.y!) / 2)
      const shift = panToReveal(point, sizeRef.current, cover, REVEAL_MARGIN)
      if (!shift.x && !shift.y) return
      const at = fg.centerAt()
      const k = fg.zoom()
      fg.centerAt(at.x - shift.x / k, at.y - shift.y / k, duration(REVEAL_MS))
      refitOnClose.current = true
    }
  })
  const revealAfterFit = (ms: number) => { timers.current.push(setTimeout(() => reveal.current(), ms + 30)) }

  useEffect(() => {
    if (growing) return
    reveal.current()
    // The panel has closed: frame everything it moved or hid.
    if (!cover.right && !cover.bottom && refitOnClose.current) {
      refitOnClose.current = false
      if (!emphasis) fgRef.current?.zoomToFit(duration(REVEAL_MS), FIT_PADDING)
    }
  }, [selectedNode, selectedEdge, cover.right, cover.bottom, growing, emphasis])

  const fitAll = () => {
    if (fitted.current || !engineStopped.current || clock.current.origin === null) return
    if (performance.now() - clock.current.origin < clock.current.end) return
    fitted.current = true
    fgRef.current?.zoomToFit(duration(FIT_MS), FIT_PADDING)
    revealAfterFit(duration(FIT_MS))
  }

  const finishGrowth = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    clock.current.origin = DONE
    setGrowing(false)
    fgRef.current?.zoomToFit(duration(FIT_MS), FIT_PADDING)
    revealAfterFit(duration(FIT_MS))
  }

  useEffect(() => {
    fitted.current = false
    engineStopped.current = false
    const fg = fgRef.current
    if (!fg) return
    // The layout decides positions. Links only draw: edge width shows palette similarity.
    fg.d3Force('charge', null as never)
    fg.d3Force('center', null as never)
    fg.d3Force('link')?.strength(0)
    fg.d3Force('layout', layoutForce() as never)
    fg.d3ReheatSimulation()

    const { fresh, animated } = data
    // Paintings added beside an open panel can land behind it.
    if (animated && !fresh && cover.right + cover.bottom > 0) refitOnClose.current = true
    if (!animated) {
      clock.current.origin ??= DONE
      setGrowing(false)
      return
    }
    if (fresh) {
      // Open close on the center painting, then pull back as the web grows.
      const scale = Math.min(sizeRef.current.width, sizeRef.current.height) * 0.42 / (2 * CENTER_RADIUS)
      fg.centerAt(0, 0)
      fg.zoom(scale)
    }
    setGrowing(true)
    const begin = () => {
      clock.current.origin ??= performance.now()
      const remaining = clock.current.end - (performance.now() - clock.current.origin)
      if (fresh) {
        // Pull back in two steps, so each ring is on screen as it arrives.
        timers.current.push(setTimeout(() => fg.zoom(Math.max(1.2, fg.zoom() * 0.45), TIMING.ringGap), TIMING.firstRing))
        timers.current.push(setTimeout(() => fg.zoomToFit(TIMING.ringGap * 2, FIT_PADDING), TIMING.firstRing + TIMING.ringGap))
      }
      timers.current.push(setTimeout(() => { setGrowing(false); fitAll() }, remaining + 30))
    }
    const clear = () => {
      timers.current.forEach(clearTimeout)
      timers.current = []
    }
    // Give the center painting a moment to load, so the dissolve starts from the real image.
    const centerNode = data.nodes.find((n) => n.id === graph.center)
    const img = centerNode?.img ? getImage(centerNode.img) : null
    if (fresh && img && !img.complete) {
      let cancelled = false
      Promise.race([img.decode().catch(() => undefined), new Promise((r) => setTimeout(r, 700))])
        .then(() => { if (!cancelled) begin() })
      return () => { cancelled = true; clear() }
    }
    begin()
    return clear
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, norm])

  // After the dots settle, frame the paintings that answer them.
  const lastFramed = useRef<typeof emphasis>(null)
  useEffect(() => {
    if (growing || emphasis === lastFramed.current) return
    const timer = setTimeout(() => {
      lastFramed.current = emphasis
      const fg = fgRef.current
      if (!fg) return
      if (emphasis) {
        const framed = framedIds(emphasis, MATCH_THRESHOLD, MIN_FRAMED)
        fg.zoomToFit(duration(FIT_MS), FIT_PADDING, (n: Node) => framed.has(n.id as NodeId))
      } else {
        fg.zoomToFit(duration(FIT_MS), FIT_PADDING)
      }
      setTimeout(() => reveal.current(), duration(FIT_MS) + 30)
    }, SETTLE_MS)
    return () => clearTimeout(timer)
  }, [emphasis, growing])

  const isActiveEdge = (l: Link) => {
    if (!selectedEdge) return false
    const [a, b] = [idOf(l.source), idOf(l.target)]
    return (a === selectedEdge.source && b === selectedEdge.target) || (a === selectedEdge.target && b === selectedEdge.source)
  }

  const radiusOf = (node: Node) => nodeRadius(node.tier ?? 'other', node.similarity ?? 0, node.selection ?? 0)

  /** Moves a node toward its selected or unselected state, by time rather than by frame. */
  const easeSelection = (node: Node) => {
    const target = node.id === selectedNode ? 1 : 0
    const now = performance.now()
    const dt = now - (node.selectionAt ?? now)
    const current = node.selection ?? 0
    node.selection = prefersReducedMotion() ? target : target + (current - target) * Math.exp(-dt / SELECTION_MS)
    node.selectionAt = now
  }

  // The question over a selected line. Kept after deselecting, so it can dissolve away.
  const question = useRef<{ edge: EdgeRef; shownAt: number; hiddenAt: number | null } | null>(null)
  const questionSprite = useRef<DissolveSprite | null>(null)
  useEffect(() => {
    const now = performance.now()
    if (selectedEdge) question.current = { edge: selectedEdge, shownAt: now, hiddenAt: null }
    else if (question.current && question.current.hiddenAt === null) question.current.hiddenAt = now
  }, [selectedEdge])

  const drawQuestion = (ctx: CanvasRenderingContext2D, scale: number) => {
    const q = question.current
    if (!q) return
    const a = nodeById.get(q.edge.source)
    const b = nodeById.get(q.edge.target)
    if (a?.x == null || b?.x == null) return
    questionSprite.current ??= makeDissolveSprite(EDGE_QUESTION, 'rgba(22, 20, 18, 0.92)', COLORS.edgeActive)
    if (!questionSprite.current) return
    const now = performance.now()
    const calm = prefersReducedMotion()
    const shown = calm ? 1 : clamp01((now - q.shownAt) / QUESTION_IN_MS)
    const gone = q.hiddenAt === null ? 0 : calm ? 1 : clamp01((now - q.hiddenAt) / QUESTION_OUT_MS)
    if (gone >= 1) {
      question.current = null
      return
    }
    drawDissolve(ctx, questionSprite.current, (a.x + b.x!) / 2, (a.y! + b.y!) / 2, scale, shown, gone)
  }

  const ageOf = (node: Node) => {
    const { origin } = clock.current
    if (origin === null) return -1 // waiting for the center image
    return performance.now() - origin - (node.birth ?? DONE)
  }

  return (
    <div ref={boxRef} className="graph" onPointerDown={() => { if (growing) finishGrowth() }}>
      {growing
        ? <button className="skip-growth secondary" onClick={finishGrowth}>Skip</button>
        : <p className="map-legend">{view === 'paintings'
            ? 'Larger = closer palette · Click a line to see why two connect'
            : 'Bright = the 5 closest palettes · Click a line to see why two connect'}</p>}
      <ForceGraph2D<Node, Link>
        ref={fgRef}
        width={size.width}
        height={size.height}
        graphData={data}
        backgroundColor="rgba(0,0,0,0)"
        autoPauseRedraw={false}
        cooldownTicks={150}
        onRenderFramePost={drawQuestion}
        onEngineStop={() => {
          engineStopped.current = true
          fitAll()
        }}
        linkWidth={(l) => (isActiveEdge(l) ? 2 : 0) + edgeWidth(l.score)}
        linkHoverPrecision={8}
        linkCanvasObjectMode={() => 'replace'}
        linkCanvasObject={(l, ctx, scale) => {
          const a = l.source as Node
          const b = l.target as Node
          if (a.x == null || b.x == null) return
          // The later-born end is the one growing; the edge reaches toward it as its tiles fly.
          const [from, to] = (a.birth ?? DONE) <= (b.birth ?? DONE) ? [a, b] : [b, a]
          const age = ageOf(to)
          if (age < 0 || ageOf(from) < 0) return
          const reach = ease(clamp01(age / TIMING.assemble))
          // Lit when picked directly, or fading with whichever end is selected.
          const highlight = isActiveEdge(l) ? 1 : Math.max(a.selection ?? 0, b.selection ?? 0)
          const spot = emphasis ? Math.min(emphasisOf(a.id as NodeId), emphasisOf(b.id as NodeId)) : 1
          const alpha = EDGE_ALPHA * (DIM_ALPHA + (1 - DIM_ALPHA) * spot) * reach
          const width = edgeWidth(l.score)
          const endX = from.x! + (to.x! - from.x!) * reach
          const endY = from.y! + (to.y! - from.y!) * reach
          ctx.beginPath()
          ctx.moveTo(from.x!, from.y!)
          ctx.lineTo(endX, endY)
          ctx.lineWidth = width / scale
          ctx.strokeStyle = `rgba(${COLORS.edge.join(',')},${alpha})`
          ctx.stroke()
          if (highlight > 0.01) {
            ctx.save()
            ctx.globalAlpha = highlight
            ctx.lineWidth = (width + 1.5) / scale
            ctx.strokeStyle = COLORS.edgeActive
            ctx.stroke()
            ctx.restore()
          }
        }}
        nodeLabel={(n) => `${n.title}${n.artist ? ` — ${n.artist}` : ''}`}
        nodeCanvasObject={(node, ctx, scale) => {
          const age = ageOf(node)
          if (age < 0) return
          easeSelection(node)
          const spot = emphasisOf(node.id as NodeId)
          const selected = node.id === selectedNode
          const r = radiusOf(node)
          ctx.save()
          const alpha = DIM_ALPHA + (1 - DIM_ALPHA) * spot
          const isCenter = node.id === graph.center
          const resting = view !== 'paintings' && node.tier === 'other'
          ctx.globalAlpha = selected ? Math.max(SELECTED_MIN_ALPHA, alpha) : resting ? alpha * REST_ALPHA : alpha
          if (isCenter && age < centerDuration) {
            drawCenterGrowth(ctx, node, r, age, view)
            ctx.restore()
            return
          }
          if (!isCenter && age < TIMING.assemble + TIMING.resolve) {
            const parent = node.parent != null ? nodeById.get(node.parent) : undefined
            drawNodeGrowth(ctx, node, parent, r, age, view)
            ctx.restore()
            return
          }
          // Faded nodes are see-through, so cover the lines that run to their centers.
          if (ctx.globalAlpha < 1) {
            const faded = ctx.globalAlpha
            ctx.globalAlpha = 1
            ctx.beginPath()
            ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
            ctx.fillStyle = COLORS.background
            ctx.fill()
            ctx.globalAlpha = faded
          }
          drawDisc(ctx, node, r, view)
          // Border in the painting's dominant color; gold is kept for the selection.
          if (selected || isCenter || view === 'paintings') {
            ctx.beginPath()
            ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
            ctx.lineWidth = (selected ? 3 : 1.5) / Math.sqrt(scale)
            ctx.strokeStyle = selected ? COLORS.ring : isCenter ? CENTER_RING : node.palette[0]?.hex ?? '#888'
            ctx.stroke()
          }
          if (node.depth === 0 || selected) {
            const fontSize = 12 / scale
            ctx.font = `${fontSize}px ${LABEL_FONT}`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            ctx.fillStyle = COLORS.label
            const label = node.title.length > 40 ? `${node.title.slice(0, 38)}…` : node.title
            ctx.fillText(label, node.x!, node.y! + r + 4 / scale)
          }
          ctx.restore()
        }}
        nodePointerAreaPaint={(node, color, ctx) => {
          if (ageOf(node) < 0) return
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x!, node.y!, radiusOf(node), 0, 2 * Math.PI)
          ctx.fill()
        }}
        onNodeClick={(n) => props.onNodeClick(n.id as NodeId)}
        onLinkClick={(l) => props.onEdgeClick({ source: idOf(l.source), target: idOf(l.target) })}
        onBackgroundClick={props.onBackgroundClick}
      />
    </div>
  )
}
