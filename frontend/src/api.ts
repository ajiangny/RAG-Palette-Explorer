// Typed client for the FastAPI backend. In dev, Vite proxies /api → localhost:8000.
const BASE: string = import.meta.env.VITE_API_URL ?? '/api'

export type Swatch = { lab: number[]; hex: string; weight: number }

export type NodeId = number | 'upload'

export type GraphNode = {
  id: NodeId
  aic_id?: number
  title: string
  artist: string | null
  date?: string | null
  style?: string | null
  image_url?: string
  palette: Swatch[]
  depth: number
}

export type GraphEdge = { source: NodeId; target: NodeId; kind: string; score: number }

export type Graph = { center: NodeId; nodes: GraphNode[]; edges: GraphEdge[] }

export type Source = { n: number; title: string; url: string; cited: boolean }

export type ColorPair = { a: string; b: string; share: number; delta_e: number }

export type EdgeExplanation = {
  source: number | null
  target: number
  palette_distance: number
  matched_colors: ColorPair[]
  answer: string
  sources: Source[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const graphFromArtwork = (id: number, k = 6, depth = 2) =>
  request<Graph>(`/graph/${id}?k=${k}&depth=${depth}`)

export function graphFromUpload(file: File, k = 6, depth = 2) {
  const form = new FormData()
  form.append('file', file)
  return request<Graph>(`/graph?k=${k}&depth=${depth}`, { method: 'POST', body: form })
}

export const randomArtwork = () => request<{ id: number; title: string; artist: string | null }>('/artworks/random')

export function explainEdge(target: number, source: number | Swatch[]) {
  const body = typeof source === 'number'
    ? { target_id: target, source_id: source }
    : { target_id: target, source_palette: source }
  return request<EdgeExplanation>('/explain-edge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** IIIF lets us ask AIC for a smaller rendition of the same image. */
export const thumbUrl = (imageUrl: string, width = 200) => imageUrl.replace('/full/843,/', `/full/${width},/`)

export const aicPage = (aicId: number) => `https://www.artic.edu/artworks/${aicId}`
