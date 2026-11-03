import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d'
import { thumbUrl, type Graph, type GraphNode, type NodeId } from '../api'

type Node = NodeObject<GraphNode & { img?: string }>
type Link = LinkObject<Node, { score: number }>

export type EdgeRef = { source: NodeId; target: NodeId }

type Props = {
  graph: Graph
  uploadPreview: string | null
  selectedNode: NodeId | null
  selectedEdge: EdgeRef | null
  onNodeClick: (id: NodeId) => void
  onEdgeClick: (edge: EdgeRef) => void
  onBackgroundClick: () => void
}

const RADIUS = [26, 17, 12, 9] // by depth from the center
const COLORS = { edge: 'rgba(232, 224, 210, 0.22)', edgeActive: '#e8c66a', ring: '#e8c66a', label: '#f2ece2' }

const idOf = (end: Link['source']): NodeId => (typeof end === 'object' ? (end as Node).id as NodeId : end as NodeId)

// One <img> per URL, shared across renders; the canvas redraws continuously so late loads show up.
const imageCache = new Map<string, HTMLImageElement>()
function getImage(src: string): HTMLImageElement {
  let img = imageCache.get(src)
  if (!img) {
    img = new Image()
    img.referrerPolicy = 'no-referrer' // AIC's CDN rejects image requests with a localhost referer
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

export default function GraphView(props: Props) {
  const { graph, uploadPreview, selectedNode, selectedEdge } = props
  const fgRef = useRef<ForceGraphMethods<Node, Link> | undefined>(undefined)
  const boxRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 800, height: 600 })
  const fitted = useRef(false)

  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ width: e.contentRect.width, height: e.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // The force engine mutates node/link objects, so hand it fresh copies per graph.
  const data = useMemo(() => {
    const nodes: Node[] = graph.nodes.map((n) => ({
      ...n,
      img: n.id === 'upload' ? uploadPreview ?? undefined : n.image_url && thumbUrl(n.image_url),
      ...(n.id === graph.center ? { fx: 0, fy: 0 } : {}),
    }))
    const links: Link[] = graph.edges.map((e) => ({ source: e.source, target: e.target, score: e.score }))
    return { nodes, links }
  }, [graph, uploadPreview])

  // Edge scores rescaled to 0–1 within this web, for width and length.
  const norm = useMemo(() => {
    const scores = graph.edges.map((e) => e.score)
    const [lo, hi] = [Math.min(...scores), Math.max(...scores)]
    return (s: number) => (hi > lo ? (s - lo) / (hi - lo) : 1)
  }, [graph])

  useEffect(() => {
    fitted.current = false
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force('charge')?.strength(-220)
    // Stronger palette similarity → shorter link.
    fg.d3Force('link')?.distance((l: Link) => 45 + (1 - norm(l.score)) * 90)
    fg.d3ReheatSimulation()
  }, [data, norm])

  const isActiveEdge = (l: Link) => {
    if (!selectedEdge) return false
    const [a, b] = [idOf(l.source), idOf(l.target)]
    return (a === selectedEdge.source && b === selectedEdge.target) || (a === selectedEdge.target && b === selectedEdge.source)
  }

  return (
    <div ref={boxRef} className="graph">
      <ForceGraph2D<Node, Link>
        ref={fgRef}
        width={size.width}
        height={size.height}
        graphData={data}
        backgroundColor="rgba(0,0,0,0)"
        autoPauseRedraw={false}
        cooldownTicks={150}
        onEngineStop={() => {
          if (!fitted.current) fgRef.current?.zoomToFit(500, 60)
          fitted.current = true
        }}
        linkWidth={(l) => (isActiveEdge(l) ? 2 : 0) + 0.6 + 6 * norm(l.score) ** 2}
        linkColor={(l) => (isActiveEdge(l) ? COLORS.edgeActive : COLORS.edge)}
        linkHoverPrecision={8}
        nodeLabel={(n) => `${n.title}${n.artist ? ` — ${n.artist}` : ''}`}
        nodeCanvasObject={(node, ctx, scale) => {
          const r = RADIUS[Math.min(node.depth, RADIUS.length - 1)]
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
          // Border in the painting's dominant color; gold ring when selected or center.
          const selected = node.id === selectedNode
          ctx.beginPath()
          ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
          ctx.lineWidth = (selected ? 3 : node.id === graph.center ? 2 : 1.5) / Math.sqrt(scale)
          ctx.strokeStyle = selected || node.id === graph.center ? COLORS.ring : node.palette[0]?.hex ?? '#888'
          ctx.stroke()
          if (node.depth === 0 || selected) {
            const fontSize = 12 / scale
            ctx.font = `${fontSize}px system-ui, sans-serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            ctx.fillStyle = COLORS.label
            const label = node.title.length > 40 ? `${node.title.slice(0, 38)}…` : node.title
            ctx.fillText(label, node.x!, node.y! + r + 4 / scale)
          }
        }}
        nodePointerAreaPaint={(node, color, ctx) => {
          const r = RADIUS[Math.min(node.depth, RADIUS.length - 1)]
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
          ctx.fill()
        }}
        onNodeClick={(n) => props.onNodeClick(n.id as NodeId)}
        onLinkClick={(l) => props.onEdgeClick({ source: idOf(l.source), target: idOf(l.target) })}
        onBackgroundClick={props.onBackgroundClick}
      />
    </div>
  )
}
