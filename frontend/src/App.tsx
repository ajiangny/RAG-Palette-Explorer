import { useCallback, useRef, useState, type DragEvent } from 'react'
import {
  explainEdge, graphFromArtwork, graphFromUpload, randomArtwork,
  type EdgeExplanation, type Graph, type GraphEdge, type NodeId,
} from './api'
import GraphView, { type EdgeRef } from './components/GraphView'
import PaletteStrip from './components/PaletteStrip'
import SidePanel from './components/SidePanel'

const edgeKey = (a: NodeId, b: NodeId) => [String(a), String(b)].sort().join('~')

export default function App() {
  const [graph, setGraph] = useState<Graph | null>(null)
  const [uploadPreview, setUploadPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<NodeId | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<EdgeRef | null>(null)
  const [explanations, setExplanations] = useState<Record<string, EdgeExplanation>>({})
  const [explaining, setExplaining] = useState<Set<string>>(new Set())
  const [explainErrors, setExplainErrors] = useState<Record<string, string>>({})
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async (message: string, fetchGraph: () => Promise<Graph>) => {
    setLoading(message)
    setError(null)
    try {
      const g = await fetchGraph()
      setGraph(g)
      setSelectedNode(g.center)
      setSelectedEdge(null)
    } catch (e) {
      setError(`Couldn't build the web (${(e as Error).message}).`)
    } finally {
      setLoading(null)
    }
  }, [])

  const onFile = (file: File | undefined) => {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('Please choose an image file.')
      return
    }
    if (uploadPreview) URL.revokeObjectURL(uploadPreview)
    setUploadPreview(URL.createObjectURL(file))
    load('Extracting your palette and finding paintings…', () => graphFromUpload(file))
  }

  const recenter = (id: number) => load('Re-centering the web…', () => graphFromArtwork(id))

  const startRandom = () => load('Picking a painting…', async () => graphFromArtwork((await randomArtwork()).id))

  const expand = async (id: number) => {
    if (!graph) return
    setLoading('Adding neighbors…')
    try {
      const more = await graphFromArtwork(id, 6, 1)
      const base = graph.nodes.find((n) => n.id === id)?.depth ?? 0
      const have = new Set(graph.nodes.map((n) => n.id))
      const haveEdges = new Set(graph.edges.map((e) => edgeKey(e.source, e.target)))
      const nodes = more.nodes.filter((n) => !have.has(n.id)).map((n) => ({ ...n, depth: base + n.depth }))
      const edges: GraphEdge[] = more.edges.filter((e) => !haveEdges.has(edgeKey(e.source, e.target)))
      setGraph({ ...graph, nodes: [...graph.nodes, ...nodes], edges: [...graph.edges, ...edges] })
    } catch (e) {
      setError(`Couldn't expand (${(e as Error).message}).`)
    } finally {
      setLoading(null)
    }
  }

  const selectEdge = async (edge: EdgeRef) => {
    setSelectedNode(null)
    setSelectedEdge(edge)
    const key = edgeKey(edge.source, edge.target)
    if (explanations[key] || explaining.has(key) || !graph) return
    // The upload has no row in the database, so it is sent as a palette.
    const upload = graph.nodes.find((n) => n.id === 'upload')
    const [src, tgt] = edge.target === 'upload' ? [edge.target, edge.source] : [edge.source, edge.target]
    setExplaining((s) => new Set(s).add(key))
    setExplainErrors((m) => {
      const next = { ...m }
      delete next[key]
      return next
    })
    try {
      const result = await explainEdge(tgt as number, src === 'upload' ? upload!.palette : (src as number))
      setExplanations((m) => ({ ...m, [key]: result }))
    } catch (e) {
      setExplainErrors((m) => ({ ...m, [key]: `Explanation failed (${(e as Error).message}).` }))
    } finally {
      setExplaining((s) => {
        const next = new Set(s)
        next.delete(key)
        return next
      })
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    onFile(e.dataTransfer.files[0])
  }

  const nodeById = (id: NodeId | null) => graph?.nodes.find((n) => n.id === id) ?? null
  const center = nodeById(graph?.center ?? null)
  // Same order as the explanation request (the upload, if any, is always the source),
  // so thumbnails line up with the matched-color pairs.
  const [edgeA, edgeB] = selectedEdge?.target === 'upload'
    ? [selectedEdge.target, selectedEdge.source]
    : [selectedEdge?.source ?? null, selectedEdge?.target ?? null]
  const edgeNodes = nodeById(edgeA) && nodeById(edgeB) ? { a: nodeById(edgeA)!, b: nodeById(edgeB)! } : null
  const key = selectedEdge && edgeKey(selectedEdge.source, selectedEdge.target)

  return (
    <div className={`app${dragging ? ' dragging' : ''}`}
         onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
         onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false) }}
         onDrop={onDrop}>
      <header>
        <h1>Palette Explorer</h1>
        {center && (
          <div className="center-palette">
            <span className="muted">{center.id === 'upload' ? 'Your palette' : center.title}</span>
            <PaletteStrip palette={center.palette} />
          </div>
        )}
        <div className="header-actions">
          <button onClick={() => fileInput.current?.click()}>Upload image</button>
          <button className="secondary" onClick={startRandom}>Random painting</button>
        </div>
        <input ref={fileInput} type="file" accept="image/*" hidden onChange={(e) => onFile(e.target.files?.[0])} />
      </header>

      {error && <div className="toast error" onClick={() => setError(null)}>{error}</div>}

      <main>
        {graph ? (
          <>
            <GraphView graph={graph} uploadPreview={uploadPreview} selectedNode={selectedNode} selectedEdge={selectedEdge}
                       onNodeClick={(id) => { setSelectedEdge(null); setSelectedNode(id) }}
                       onEdgeClick={selectEdge}
                       onBackgroundClick={() => { setSelectedNode(null); setSelectedEdge(null) }} />
            <SidePanel node={nodeById(selectedNode)} edge={edgeNodes}
                       explanation={key ? explanations[key] ?? null : null}
                       explaining={!!key && explaining.has(key)}
                       explainError={key ? explainErrors[key] ?? null : null}
                       uploadPreview={uploadPreview} isCenter={selectedNode === graph.center}
                       onRecenter={recenter} onExpand={expand}
                       onClose={() => { setSelectedNode(null); setSelectedEdge(null) }} />
          </>
        ) : (
          <div className="empty">
            <div className="dropzone" onClick={() => fileInput.current?.click()}>
              <h2>Drop an image to find paintings with its palette</h2>
              <p className="muted">A photo, a screenshot, a design. We extract its colors and build a web of
                public-domain paintings from the Art Institute of Chicago with similar palettes.</p>
              <button>Choose an image</button>
            </div>
            <button className="link" onClick={startRandom}>or start from a random painting</button>
          </div>
        )}
        {loading && <div className="loading"><span className="spinner" />{loading}</div>}
      </main>
    </div>
  )
}
