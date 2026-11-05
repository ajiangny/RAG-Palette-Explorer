import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import {
  explainEdge, graphFromArtwork, graphFromUpload, randomArtwork, wakeBackend,
  type EdgeExplanation, type Graph, type GraphEdge, type NodeId,
} from './api'
import GraphView, { type EdgeRef, type MapView } from './components/GraphView'
import PaletteEditor from './components/PaletteEditor'
import SidePanel from './components/SidePanel'
import { bestMatch, loadCollection, makeDeck, type Painting } from './lib/collection'
import { hexToLab } from './lib/color'
import { MAX_DOTS, readUrl, writeUrl } from './lib/queryPalette'

const edgeKey = (a: NodeId, b: NodeId) => [String(a), String(b)].sort().join('~')
const MATCH_SETTLE_MS = 300
const VIEWS: [MapView, string][] = [['paintings', 'Paintings'], ['pixels', 'Pixels'], ['blocks', 'Blocks']]
const PHONE_QUERY = '(max-width: 760px)'
/** Matches --panel-width in index.css. */
const panelWidth = () => Math.min(720, Math.max(420, window.innerWidth * 0.44))

const SLOW_AFTER_MS = 6000

export default function App() {
  const [graph, setGraph] = useState<Graph | null>(null)
  // Counts webs built from scratch; expanding one keeps the count, so only its new nodes grow.
  const [generation, setGeneration] = useState(0)
  const [uploadPreview, setUploadPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [slow, setSlow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<NodeId | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<EdgeRef | null>(null)
  const [explanations, setExplanations] = useState<Record<string, EdgeExplanation>>({})
  const [explaining, setExplaining] = useState<Set<string>>(new Set())
  const [explainErrors, setExplainErrors] = useState<Record<string, string>>({})
  const [dragging, setDragging] = useState(false)
  const [view, setView] = useState<MapView>('paintings')
  const fileInput = useRef<HTMLInputElement>(null)
  const [initialUrl] = useState(() => readUrl(window.location.search))
  // The user's colors. Null until they edit a dot; the dots then show the center painting's colors.
  const [query, setQuery] = useState<string[] | null>(initialUrl.palette)
  const [collection, setCollection] = useState<Painting[] | null>(null)
  const [match, setMatch] = useState<Painting | null>(null)
  const deal = useMemo(() => (collection?.length ? makeDeck(collection) : null), [collection])

  const load = useCallback(async (message: string, fetchGraph: () => Promise<Graph>) => {
    setLoading(message)
    setError(null)
    try {
      const g = await fetchGraph()
      setGraph(g)
      setGeneration((n) => n + 1)
      setSelectedNode(null)
      setSelectedEdge(null)
    } catch (e) {
      setError(`Couldn't build the web (${(e as Error).message}).`)
    } finally {
      setLoading(null)
    }
  }, [])

  useEffect(() => { void wakeBackend() }, [])

  // The free backend sleeps when idle, so say why a first request can take a while.
  useEffect(() => {
    if (!loading) return
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS)
    return () => {
      clearTimeout(timer)
      setSlow(false)
    }
  }, [loading])

  // Everything needed to run the palette works in the browser, so fetch it once, in the background.
  useEffect(() => {
    let cancelled = false
    loadCollection()
      .then((c) => { if (!cancelled) setCollection(c) })
      .catch(() => { /* Surprise me and the closest painting stay off; Spotlight still works */ })
    return () => { cancelled = true }
  }, [])

  // Open a shared link: its painting if it names one, otherwise the closest match to its colors.
  const opened = useRef(false)
  useEffect(() => {
    if (opened.current) return
    if (initialUrl.center != null) {
      opened.current = true
      load('Growing the web…', () => graphFromArtwork(initialUrl.center!))
    } else if (initialUrl.palette && collection) {
      opened.current = true
      const best = bestMatch(collection, initialUrl.palette.map(hexToLab))
      if (best) load('Growing the web…', () => graphFromArtwork(best.id))
    }
  }, [collection, initialUrl, load])

  // Keep the current web and colors in the address bar, so a view can be shared or reloaded.
  useEffect(() => {
    if (!graph) return
    const center = typeof graph.center === 'number' ? graph.center : null
    // Debounced: browsers throttle history updates, and a slider drag would exceed the limit.
    const timer = setTimeout(() => {
      window.history.replaceState(null, '', `${window.location.pathname}${writeUrl({ center, palette: query })}`)
    }, MATCH_SETTLE_MS)
    return () => clearTimeout(timer)
  }, [graph, query])

  // The collection's closest painting to the dots, once they stop moving.
  useEffect(() => {
    if (!query?.length || !collection) return
    const timer = setTimeout(() => setMatch(bestMatch(collection, query.map(hexToLab), graph?.center)), MATCH_SETTLE_MS)
    return () => clearTimeout(timer)
  }, [query, collection, graph?.center])

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
      console.warn('Explanation failed', e)
      setExplainErrors((m) => ({ ...m, [key]: 'Couldn\u2019t load the explanation. Click the line to try again.' }))
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
  const dots = query ?? center?.palette.slice(0, MAX_DOTS).map((s) => s.hex) ?? []
  // Same order as the explanation request (the upload, if any, is always the source),
  // so thumbnails line up with the matched-color pairs.
  const [edgeA, edgeB] = selectedEdge?.target === 'upload'
    ? [selectedEdge.target, selectedEdge.source]
    : [selectedEdge?.source ?? null, selectedEdge?.target ?? null]
  const edgeNodes = nodeById(edgeA) && nodeById(edgeB) ? { a: nodeById(edgeA)!, b: nodeById(edgeB)! } : null
  const key = selectedEdge && edgeKey(selectedEdge.source, selectedEdge.target)
  const panelOpen = !!nodeById(selectedNode) || !!edgeNodes
  // What the panel hides of the map: the right side, or the bottom on phones. Matches the CSS.
  const cover = !panelOpen
    ? { right: 0, bottom: 0 }
    : window.matchMedia(PHONE_QUERY).matches
      ? { right: 0, bottom: Math.round(window.innerHeight * 0.55) }
      : { right: panelWidth(), bottom: 0 }

  return (
    <div className={`app${dragging ? ' dragging' : ''}${panelOpen ? ' panel-open' : ''}`}
         onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
         onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false) }}
         onDrop={onDrop}>
      <header>
        <h1>Palette Explorer</h1>
        {graph && (
          <>
            <div className="view-switch" role="group" aria-label="Show the web as">
              {VIEWS.map(([id, label]) => (
                <button key={id} className={view === id ? 'on' : ''} aria-pressed={view === id} onClick={() => setView(id)}>{label}</button>
              ))}
            </div>
            <div className="header-actions">
              <button className="secondary" onClick={startRandom}>Random</button>
              <button onClick={() => fileInput.current?.click()}>Upload</button>
            </div>
          </>
        )}
        <input ref={fileInput} type="file" accept="image/*" hidden onChange={(e) => onFile(e.target.files?.[0])} />
      </header>

      {error && <div className="toast error" onClick={() => setError(null)}>{error}</div>}

      <main>
        {graph ? (
          <>
            <div className="graph-area">
              <GraphView graph={graph} uploadPreview={uploadPreview} selectedNode={selectedNode} selectedEdge={selectedEdge}
                         generation={generation} query={query} view={view} cover={cover}
                         onNodeClick={(id) => { setSelectedEdge(null); setSelectedNode(id) }}
                         onEdgeClick={selectEdge}
                         onBackgroundClick={() => { setSelectedNode(null); setSelectedEdge(null) }} />
              <PaletteEditor colors={dots} active={!!query} onChange={setQuery} onClear={() => setQuery(null)}
                             onSurprise={deal && (() => setQuery(deal()))}
                             match={query && match ? { title: match.title, onGrow: () => recenter(match.id) } : null} />
            </div>
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
              <p className="muted">Public-domain paintings from the Art Institute of Chicago, the Cleveland Museum of Art and the National Gallery of Art.</p>
              <button>Choose an image</button>
            </div>
            <button className="link" onClick={startRandom}>or start from a random painting</button>
          </div>
        )}
        {loading && (
          <div className="loading">
            <span className="spinner" />
            {slow ? 'The free server is waking up. This can take about a minute…' : loading}
          </div>
        )}
      </main>
    </div>
  )
}
