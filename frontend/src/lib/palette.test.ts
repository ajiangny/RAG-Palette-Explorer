import assert from 'node:assert/strict'
import { test } from 'node:test'
import { colorName, hexToHsv, hexToLab, hexToOklch, hsvToHex, oklchToHex, paletteBands } from './color.ts'
import { bestMatch, makeDeck, parseItems } from './collection.ts'
import { CENTER_RADIUS, centerDuration, growthEnd, nodeRadius, planBirths, TIMING, type SizeTier } from './growth.ts'
import { panToReveal, radialLayout } from './layout.ts'
import { MAX_DOTS, formatPalette, parsePalette, readUrl, shuffleHues, writeUrl } from './queryPalette.ts'
import { chamfer, closestIds, emphasize, framedIds, lambdaFor, paletteDistance, similarityToCenter } from './spotlight.ts'

const close = (a: number, b: number, eps = 0.05) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`)

test('hexToLab matches the reference values the backend uses (skimage, D65)', () => {
  const [l, a, b] = hexToLab('#ff0000')
  close(l, 53.24); close(a, 80.09); close(b, 67.2)
  const white = hexToLab('#ffffff')
  close(white[0], 100); close(white[1], 0); close(white[2], 0)
})

test('oklch round-trips in-gamut colors', () => {
  for (const hex of ['#8a5a3c', '#1d2a4a', '#e8c66a', '#808080']) assert.equal(oklchToHex(hexToOklch(hex)), hex)
})

test('hsv round-trips colors, and reads the primaries correctly', () => {
  for (const hex of ['#5f7318', '#c79463', '#8a5a3c', '#1d2a4a', '#808080', '#000000', '#ffffff', '#ff00ff']) {
    assert.equal(hsvToHex(hexToHsv(hex)), hex)
  }
  assert.deepEqual(hexToHsv('#ff0000'), { h: 0, s: 1, v: 1 })
  assert.deepEqual(hexToHsv('#00ff00'), { h: 120, s: 1, v: 1 })
  assert.deepEqual(hexToHsv('#0000ff'), { h: 240, s: 1, v: 1 })
  assert.equal(hsvToHex({ h: 360, s: 1, v: 1 }), '#ff0000')
  assert.equal(hsvToHex({ h: 200, s: 0, v: 0.5 }), '#808080')
})

test('oklchToHex keeps out-of-gamut colors valid, with lightness near the request', () => {
  const hex = oklchToHex({ l: 0.7, c: 0.37, h: 200 })
  assert.match(hex, /^#[0-9a-f]{6}$/)
  close(hexToOklch(hex).l, 0.7, 0.01)
})

test('colorName gives usable words', () => {
  assert.equal(colorName('#000000'), 'black')
  assert.equal(colorName('#ffffff'), 'white')
  assert.equal(colorName('#2f55c4'), 'blue')
  assert.equal(colorName('#8a5a3c'), 'brown')
})

const swatch = (hex: string, weight: number) => ({ lab: hexToLab(hex), weight })

test('chamfer scores an identical palette as zero and an opposite one as far', () => {
  const palette = [swatch('#ff0000', 0.5), swatch('#0000ff', 0.5)]
  const query = [hexToLab('#ff0000'), hexToLab('#0000ff')]
  close(chamfer(query, palette), 0)
  assert.ok(chamfer([hexToLab('#00ff00')], palette) > 50)
})

test('a single dot asks only whether the painting contains the color', () => {
  assert.equal(lambdaFor(1), 0)
  const blueDominated = [swatch('#0000ff', 0.95), swatch('#ff0000', 0.05)]
  close(chamfer([hexToLab('#ff0000')], blueDominated), 0)
})

test('five dots penalize a painting whose weight sits on colors outside the query', () => {
  const query = ['#ff0000', '#ff2200', '#ee0000', '#dd0000', '#cc0000'].map(hexToLab)
  const allRed = [swatch('#ff0000', 1)]
  const mostlyBlue = [swatch('#ff0000', 0.1), swatch('#0000ff', 0.9)]
  assert.ok(chamfer(query, mostlyBlue) > chamfer(query, allRed) + 20)
})

test('chamfer treats empty input as no match', () => {
  assert.equal(chamfer([], [swatch('#000000', 1)]), Infinity)
  assert.equal(chamfer([hexToLab('#000000')], []), Infinity)
})

test('emphasize ranks the closest at 1, and flat scores all at 1', () => {
  const e = emphasize(new Map<number, number>([[1, 10], [2, 30], [3, Infinity]]))
  assert.equal(e.get(1), 1)
  assert.equal(e.get(2), 0)
  assert.equal(e.get(3), 0)
  assert.equal(emphasize(new Map([[1, 10], [2, 10.5]])).get(2), 1)
})

test('one near-perfect outlier does not wash out the rest', () => {
  const e = emphasize(new Map([['center', 1], ['a', 30], ['b', 31], ['c', 32], ['d', 60]]))
  assert.equal(e.get('center'), 1)
  assert.ok(e.get('a')! > 0.5, 'the next-best painting stays visible')
  assert.ok(e.get('b')! > e.get('c')!)
})

test('framing always includes several paintings, so the camera cannot dive into one', () => {
  const e = new Map([[1, 1], [2, 0.2], [3, 0.1], [4, 0.05], [5, 0]])
  assert.deepEqual([...framedIds(e, 0.5, 3)].sort(), [1, 2, 3])
  assert.equal(framedIds(new Map([[1, 0.9], [2, 0.8], [3, 0.7]]), 0.5, 1).size, 3)
})

test('palette URL round-trips, and bad input is dropped', () => {
  const hexes = ['#b38856', '#d16f58']
  assert.deepEqual(parsePalette(formatPalette(hexes)), hexes)
  assert.equal(parsePalette(null), null)
  assert.equal(parsePalette('nope-xyz'), null)
  assert.deepEqual(parsePalette('B38856-nope'), ['#b38856'])
  assert.equal(parsePalette('000000-111111-222222-333333-444444-555555')!.length, MAX_DOTS)
  assert.deepEqual(readUrl(writeUrl({ center: 12, palette: hexes })), { center: 12, palette: hexes })
  assert.deepEqual(readUrl('?c=abc'), { center: null, palette: null })
  assert.equal(writeUrl({ center: null, palette: null }), '')
})

test('shuffling rotates hue and keeps lightness', () => {
  const [before] = ['#8a5a3c']
  const [after] = shuffleHues([before], () => 0.5)
  assert.notEqual(after, before)
  close(hexToOklch(after).l, hexToOklch(before).l, 0.01)
})

const paintings = parseItems([
  { id: 1, t: 'Red', c: 'ff0000', w: [1] },
  { id: 2, t: 'Blue', c: '0000ff', w: [1] },
  { id: 3, t: 'Six', c: '000000111111222222333333444444555555', w: [0.5, 0.2, 0.1, 0.1, 0.05, 0.05] },
])

test('bestMatch finds the nearest painting and honors exclude', () => {
  assert.equal(bestMatch(paintings, [hexToLab('#ee1111')])!.id, 1)
  // With red excluded, near-black is closer to red than saturated blue is, in CIELAB.
  assert.equal(bestMatch(paintings, [hexToLab('#ee1111')], 1)!.id, 3)
  assert.equal(bestMatch(paintings, [hexToLab('#1111ee')], 2)!.id, 3)
})

test('the deck deals every painting once before repeating, at most five colors each', () => {
  const deal = makeDeck(paintings, () => 0.3)
  const dealt = [deal(), deal(), deal()]
  assert.equal(new Set(dealt.map((d) => d[0])).size, 3)
  assert.ok(dealt.every((d) => d.length <= MAX_DOTS))
  assert.deepEqual(deal(), dealt[0])
})

const nodes = [
  { id: 'c', depth: 0 },
  { id: 'a', depth: 1 }, { id: 'b', depth: 1 },
  { id: 'x', depth: 2 },
]
const edges = [
  { source: 'c', target: 'a', score: 0.9 },
  { source: 'c', target: 'b', score: 0.8 },
  { source: 'a', target: 'x', score: 0.5 },
  { source: 'b', target: 'x', score: 0.7 },
]

test('a new web grows ring by ring, each node leaving its strongest closer neighbor', () => {
  const plan = planBirths(nodes, edges, 'c')
  assert.deepEqual(plan.get('c'), { birth: 0, parent: null })
  assert.equal(plan.get('a')!.birth, TIMING.firstRing)
  assert.equal(plan.get('a')!.parent, 'c')
  assert.equal(plan.get('x')!.parent, 'b')
  assert.ok(plan.get('x')!.birth >= plan.get('b')!.birth)
  assert.ok(growthEnd(plan) >= centerDuration)
})

test('expanding grows only the new nodes, out of the expanded painting, right away', () => {
  const plan = planBirths(nodes, edges, 'c', new Set(['c', 'a', 'b']))
  assert.deepEqual([...plan.keys()], ['x'])
  assert.equal(plan.get('x')!.birth, 0)
  assert.equal(plan.get('x')!.parent, 'b')
})

test('a large ring still starts within the spread', () => {
  const many = [{ id: 'c', depth: 0 }, ...Array.from({ length: 150 }, (_, i) => ({ id: i, depth: 1 }))]
  const plan = planBirths(many, [], 'c')
  assert.ok(plan.get(149)!.birth - plan.get(0)!.birth <= TIMING.ringSpread)
})

test('the center is the largest circle, whatever the similarity or selection', () => {
  assert.equal(nodeRadius('center', 1, 0), CENTER_RADIUS)
  for (const similarity of [0, 0.5, 1]) {
    for (const selection of [0, 0.5, 1]) assert.ok(nodeRadius('closest', similarity, selection) < CENTER_RADIUS)
  }
})

test('the closest palettes are much larger than the rest, so size never disagrees with similarity', () => {
  assert.ok(nodeRadius('closest', 0, 0) > nodeRadius('other', 1, 0))
  assert.ok(nodeRadius('closest', 1, 0) > 2 * nodeRadius('other', 1, 0))
})

test('paletteBands keep the largest five colors, filling the height in order of share', () => {
  const palette = [1, 5, 2, 8, 3, 4].map((weight, i) => ({ hex: `#00000${i}`, weight }))
  const bands = paletteBands(palette)
  assert.deepEqual(bands.map((b) => b.hex), ['#000003', '#000001', '#000005', '#000004', '#000002'])
  assert.equal(bands[0].from, 0)
  assert.equal(bands[4].to, 1)
  close(bands[0].to, 8 / 22, 0.001)
  for (let i = 1; i < 5; i++) assert.equal(bands[i].from, bands[i - 1].to)
  assert.deepEqual(paletteBands([]), [])
})

test('closestIds picks the most similar paintings and never the center', () => {
  const similarity = new Map([[0, 1], [1, 0.2], [2, 0.9], [3, 0.5], [4, 0], [5, 0.7], [6, 0.8], [7, 0.1]])
  assert.deepEqual([...closestIds(similarity, 0)].sort(), [1, 2, 3, 5, 6])
  assert.equal(closestIds(new Map([[0, 1], [1, 0.5]]), 0).size, 1)
})

test('more similar paintings are larger, by area, and selecting grows a node slightly', () => {
  const [low, mid, high] = [0, 0.5, 1].map((s) => nodeRadius('other', s, 0))
  assert.ok(low < mid && mid < high)
  close(mid ** 2 - low ** 2, high ** 2 - mid ** 2, 0.001)
  const selected = nodeRadius('other', 0.5, 1)
  assert.ok(selected > mid && selected < mid * 1.5)
})

const flat = (hex: string) => [{ lab: hexToLab(hex), weight: 1 }]

test('paletteDistance is zero for a match, symmetric, and counts pixel share', () => {
  close(paletteDistance(flat('#aa3322'), flat('#aa3322')), 0)
  const a = [swatch('#ff0000', 0.9), swatch('#0000ff', 0.1)]
  const b = [swatch('#ff0000', 0.1), swatch('#0000ff', 0.9)]
  close(paletteDistance(a, b), paletteDistance(b, a))
  assert.equal(paletteDistance([], a), Infinity)
})

test('similarityToCenter ranges 0–1 across the web, ordered by palette distance', () => {
  const sim = similarityToCenter([
    { id: 'c', palette: flat('#cc2222') },
    { id: 'near', palette: flat('#bb3333') },
    { id: 'mid', palette: flat('#886633') },
    { id: 'far', palette: flat('#2233cc') },
  ], 'c')
  assert.equal(sim.get('near'), 1)
  assert.equal(sim.get('far'), 0)
  assert.ok(sim.get('mid')! > 0 && sim.get('mid')! < 1)
})

test('similarityToCenter handles identical paintings and missing palettes', () => {
  const same = similarityToCenter([
    { id: 'c', palette: flat('#000000') }, { id: 'a', palette: flat('#808080') }, { id: 'b', palette: flat('#808080') },
  ], 'c')
  assert.equal(same.get('a'), same.get('b'))
  assert.equal(similarityToCenter([{ id: 'c', palette: [] }, { id: 'a', palette: flat('#000000') }], 'c').get('a'), 0)
})

// A web shaped like the real thing: six hubs, each with six children, plus a few cross-links.
function sampleWeb() {
  const nodes: { id: number; depth: number }[] = [{ id: 0, depth: 0 }]
  const edges: { source: number; target: number; score: number }[] = []
  let next = 7
  for (let hub = 1; hub <= 6; hub++) {
    nodes.push({ id: hub, depth: 1 })
    edges.push({ source: 0, target: hub, score: 0.5 })
    for (let k = 0; k < 6; k++) {
      nodes.push({ id: next, depth: 2 })
      edges.push({ source: hub, target: next, score: 0.8 })
      next++
    }
  }
  edges.push({ source: 1, target: 4, score: 0.3 }, { source: 2, target: 5, score: 0.3 })
  return { nodes, edges }
}

test('the layout puts the center in the middle and each depth on its own ring', () => {
  const { nodes, edges } = sampleWeb()
  const at = radialLayout(nodes, edges, 0)
  assert.equal(at.size, nodes.length)
  close(Math.hypot(at.get(0)!.x, at.get(0)!.y), 0)
  const radiusOf = (id: number) => Math.hypot(at.get(id)!.x, at.get(id)!.y)
  for (const n of nodes.filter((m) => m.depth === 1)) close(radiusOf(n.id), radiusOf(1))
  for (const n of nodes.filter((m) => m.depth === 2)) close(radiusOf(n.id), radiusOf(7))
  assert.ok(radiusOf(7) > radiusOf(1))
})

test('no two nodes overlap, and children sit close to their parent', () => {
  const { nodes, edges } = sampleWeb()
  // The largest circles can land on any ring, including side by side on the outer one.
  const closest = new Set([1, 7, 8, 9, 20])
  const tierOf = (id: number) => (id === 0 ? 'center' : closest.has(id) ? 'closest' : 'other') as SizeTier
  const sizeOf = (id: number) => nodeRadius(tierOf(id), 1, 0)
  const at = radialLayout(nodes, edges, 0, sizeOf)
  const distance = (a: number, b: number) => Math.hypot(at.get(a)!.x - at.get(b)!.x, at.get(a)!.y - at.get(b)!.y)
  // Worst case for each pair: both at their largest, with the bigger one selected.
  for (const a of nodes) {
    for (const b of nodes) {
      if (a.id >= b.id) continue
      const [big, small] = sizeOf(a.id) >= sizeOf(b.id) ? [a, b] : [b, a]
      const room = nodeRadius(tierOf(big.id), 1, 1) + sizeOf(small.id)
      assert.ok(distance(a.id, b.id) > room, `${a.id} and ${b.id} overlap`)
    }
  }
  for (const e of edges.filter((x) => x.score === 0.8)) assert.ok(distance(e.source, e.target) < 260)
})

test('a crowded ring moves outward instead of overlapping', () => {
  const nodes = [{ id: 0, depth: 0 }, ...Array.from({ length: 60 }, (_, i) => ({ id: i + 1, depth: 1 }))]
  const at = radialLayout(nodes, [], 0)
  const [a, b] = [at.get(1)!, at.get(2)!]
  assert.ok(Math.hypot(a.x - b.x, a.y - b.y) > 50)
})

test('the same web always lays out the same way, and short links win', () => {
  const { nodes, edges } = sampleWeb()
  assert.deepEqual([...radialLayout(nodes, edges, 0)], [...radialLayout(nodes, edges, 0)])
  const at = radialLayout(nodes, edges, 0)
  const crossLink = Math.hypot(at.get(1)!.x - at.get(4)!.x, at.get(1)!.y - at.get(4)!.y)
  assert.ok(crossLink < 2 * Math.hypot(at.get(1)!.x, at.get(1)!.y) * 0.9, 'cross-linked hubs are pulled together')
})

test('panToReveal leaves a visible point alone', () => {
  const shift = panToReveal({ x: 500, y: 300 }, { width: 1400, height: 800 }, { right: 376, bottom: 0 }, 48)
  assert.equal(shift.x, 0)
  assert.equal(shift.y, 0)
})

test('panToReveal moves a point out from under a right-hand panel, by just enough', () => {
  const shift = panToReveal({ x: 1200, y: 300 }, { width: 1400, height: 800 }, { right: 376, bottom: 0 }, 48)
  assert.equal(shift.x, 976 - 1200)
  assert.equal(shift.y, 0)
})

test('panToReveal moves a point up from under a bottom sheet', () => {
  const shift = panToReveal({ x: 200, y: 700 }, { width: 390, height: 844 }, { right: 0, bottom: 464 }, 48)
  assert.equal(shift.x, 0)
  assert.equal(shift.y, 332 - 700)
})
