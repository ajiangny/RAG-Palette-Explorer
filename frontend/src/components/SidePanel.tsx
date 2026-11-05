import { Fragment, useState } from 'react'
import { MUSEUMS, MUSEUM_SHORT, imageSrc, type EdgeExplanation, type GraphNode, type Source } from '../api'
import PaletteStrip from './PaletteStrip'

type Props = {
  node: GraphNode | null
  edge: { a: GraphNode; b: GraphNode } | null
  explanation: EdgeExplanation | null
  explaining: boolean
  explainError: string | null
  uploadPreview: string | null
  isCenter: boolean
  onRecenter: (id: number) => void
  onExpand: (id: number) => void
  onClose: () => void
}

/** Shows our small copy straight away, then the museum's larger one over it. Stays small if that fails. */
function Thumb({ node, preview }: { node: GraphNode; preview: string | null }) {
  const [failed, setFailed] = useState(false)
  const small = node.id === 'upload' ? preview : node.image_id && imageSrc(node.image_id)
  const src = (!failed && node.image_url) || small
  if (!src) return null
  return <img className="thumb" src={src} alt={node.title} onError={() => setFailed(true)}
              style={small ? { backgroundImage: `url("${small}")` } : undefined} />
}

/** Render "... *Title* text [2][3]." with *x* in italics and each [n] as a superscript link to its source. */
function Cited({ text, sources }: { text: string; sources: Source[] }) {
  const byN = new Map(sources.map((s) => [s.n, s]))
  return (
    <>
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i}>
          {para.split(/(\[\d+\]|\*[^*\n]+\*)/).map((part, j) => {
            const m = part.match(/^\[(\d+)\]$/)
            const src = m && byN.get(Number(m[1]))
            if (src) return <a key={j} className="cite" href={src.url} target="_blank" rel="noreferrer" title={src.title}>[{src.n}]</a>
            return /^\*.+\*$/.test(part) ? <em key={j}>{part.slice(1, -1)}</em> : <Fragment key={j}>{part}</Fragment>
          })}
        </p>
      ))}
    </>
  )
}

function NodeDetails({ node, preview, isCenter, onRecenter, onExpand }:
  { node: GraphNode; preview: string | null; isCenter: boolean; onRecenter: (id: number) => void; onExpand: (id: number) => void }) {
  const id = node.id
  return (
    <>
      <Thumb key={node.id} node={node} preview={preview} />
      <h2>{node.title}</h2>
      <p className="meta">{[node.artist, node.date, node.style].filter(Boolean).join(' · ') || 'Your uploaded image'}</p>
      {node.source && <p className="meta">{MUSEUMS[node.source]}</p>}
      <PaletteStrip palette={node.palette} />
      {typeof id === 'number' && (
        <div className="actions">
          {!isCenter && <button onClick={() => onRecenter(id)}>Re-center here</button>}
          <button className="secondary" onClick={() => onExpand(id)}>Expand neighbors</button>
          {node.source && node.source_url && (
            <a className="button secondary" href={node.source_url} target="_blank" rel="noreferrer">
              View at {MUSEUM_SHORT[node.source]} ↗
            </a>
          )}
        </div>
      )}
    </>
  )
}

function EdgeDetails({ a, b, explanation, explaining, explainError, preview }:
  { a: GraphNode; b: GraphNode; explanation: EdgeExplanation | null; explaining: boolean; explainError: string | null; preview: string | null }) {
  return (
    <>
      <div className="pair">
        <figure><Thumb key={a.id} node={a} preview={preview} /><figcaption>{a.title}</figcaption></figure>
        <figure><Thumb key={b.id} node={b} preview={preview} /><figcaption>{b.title}</figcaption></figure>
      </div>
      {explanation && (
        <>
          <h3>Matched colors</h3>
          <ul className="pairs">
            {explanation.matched_colors.slice(0, 5).map((p) => (
              <li key={`${p.a}${p.b}`}>
                <span className="chip" style={{ background: p.a }} />
                <span className="chip" style={{ background: p.b }} />
                <span>{(p.share * 100).toFixed(0)}% of pixels · ΔE {p.delta_e}</span>
              </li>
            ))}
          </ul>
          <h3>Why they connect</h3>
          <div className="answer"><Cited text={explanation.answer} sources={explanation.sources} /></div>
          {explanation.sources.some((s) => s.cited) && (
            <>
              <h3>Sources</h3>
              <ol className="sources">
                {explanation.sources.filter((s) => s.cited).map((s) => (
                  <li key={s.n} value={s.n}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>
                ))}
              </ol>
            </>
          )}
        </>
      )}
      {explaining && <p className="muted pulse">Reading sources and writing an explanation…</p>}
      {explainError && <p className="error">{explainError}</p>}
    </>
  )
}

export default function SidePanel(props: Props) {
  const { node, edge } = props
  if (!node && !edge) return null
  return (
    <aside className="panel">
      <button className="close" onClick={props.onClose} aria-label="Close">×</button>
      {node && <NodeDetails node={node} preview={props.uploadPreview} isCenter={props.isCenter}
                            onRecenter={props.onRecenter} onExpand={props.onExpand} />}
      {edge && <EdgeDetails a={edge.a} b={edge.b} explanation={props.explanation} explaining={props.explaining}
                            explainError={props.explainError} preview={props.uploadPreview} />}
    </aside>
  )
}
