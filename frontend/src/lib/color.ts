// Color conversions used by the palette editor and the Spotlight score.
// CIELAB (D65) matches the values the backend stores, so client scores and server palettes share a space.
// OKLCH is for Shuffle, because rotating its hue keeps lightness steady. HSV is for the color picker,
// because its square and hue strip show every color directly.

export type Lab = [number, number, number]
export type Oklch = { l: number; c: number; h: number }
export type Hsv = { h: number; s: number; v: number }
type Rgb = [number, number, number]

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const toLinear = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
const toGamma = (v: number) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055)

export const isHex = (s: string) => /^#?[0-9a-f]{6}$/i.test(s)

export function normalizeHex(s: string): string {
  return `#${s.replace('#', '').toLowerCase()}`
}

export function hexToRgb(hex: string): Rgb {
  const h = hex.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as Rgb
}

function rgbToHex(rgb: Rgb): string {
  return `#${rgb.map((v) => Math.round(clamp01(v) * 255).toString(16).padStart(2, '0')).join('')}`
}

export function rgbToLab([r8, g8, b8]: Rgb): Lab {
  const [r, g, b] = [r8, g8, b8].map((v) => toLinear(v / 255))
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116)
  const fx = f((0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047)
  const fy = f(0.2126729 * r + 0.7151522 * g + 0.072175 * b)
  const fz = f((0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883)
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)]
}

export const hexToLab = (hex: string): Lab => rgbToLab(hexToRgb(hex))

export function hexToOklch(hex: string): Oklch {
  const [r, g, b] = hexToRgb(hex).map((v) => toLinear(v / 255))
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
  return {
    l: 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    c: Math.hypot(a, bb),
    h: (Math.atan2(bb, a) * 180 / Math.PI + 360) % 360,
  }
}

function oklchToLinear({ l, c, h }: Oklch): Rgb {
  const a = c * Math.cos(h * Math.PI / 180)
  const b = c * Math.sin(h * Math.PI / 180)
  const L = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const M = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const S = (l - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [
    4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S,
    -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S,
    -0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S,
  ]
}

const EPS = 0.001
const inGamut = (rgb: Rgb) => rgb.every((v) => v >= -EPS && v <= 1 + EPS)

/** Colors outside sRGB keep their lightness and hue and lose chroma until they fit. */
export function oklchToHex(color: Oklch): string {
  let lo = 0
  let hi = color.c
  if (!inGamut(oklchToLinear(color))) {
    for (let i = 0; i < 16; i++) {
      const mid = (lo + hi) / 2
      if (inGamut(oklchToLinear({ ...color, c: mid }))) lo = mid
      else hi = mid
    }
  } else {
    lo = color.c
  }
  return rgbToHex(oklchToLinear({ ...color, c: lo }).map((v) => toGamma(clamp01(v))) as Rgb)
}

const HUES: [number, string][] = [
  [20, 'red'], [50, 'orange'], [75, 'ochre'], [110, 'yellow'], [150, 'green'], [195, 'teal'],
  [285, 'blue'], [320, 'violet'], [355, 'magenta'], [361, 'red'],
]

/** A rough spoken name for a dot's aria-label. Screen readers can't read a hex color usefully. */
export function colorName(hex: string): string {
  const { l, c, h } = hexToOklch(hex)
  if (c < 0.025) return l > 0.93 ? 'white' : l < 0.2 ? 'black' : l > 0.65 ? 'light gray' : l < 0.4 ? 'dark gray' : 'gray'
  const hue = HUES.find(([end]) => h < end)![1]
  if (h >= 30 && h < 90 && l < 0.62 && c < 0.13) return l < 0.35 ? 'dark brown' : 'brown'
  return `${l > 0.78 ? 'light ' : l < 0.42 ? 'dark ' : ''}${c < 0.06 ? 'muted ' : ''}${hue}`
}

/** A palette's largest colors as solid bands, largest first, each as tall as its share of them. */
export function paletteBands(palette: { hex: string; weight: number }[], limit = 5): { from: number; to: number; hex: string }[] {
  const kept = [...palette].sort((a, b) => b.weight - a.weight).slice(0, limit)
  const total = kept.reduce((sum, s) => sum + s.weight, 0)
  if (total <= 0) return []
  let before = 0
  return kept.map((s) => {
    const from = before / total
    before += s.weight
    return { from, to: before / total, hex: s.hex }
  })
}

export function hexToHsv(hex: string): Hsv {
  const [r, g, b] = hexToRgb(hex).map((c) => c / 255)
  const max = Math.max(r, g, b)
  const range = max - Math.min(r, g, b)
  let h = 0
  if (range > 0) {
    if (max === r) h = ((g - b) / range + 6) % 6
    else if (max === g) h = (b - r) / range + 2
    else h = (r - g) / range + 4
  }
  return { h: h * 60, s: max ? range / max : 0, v: max }
}

export function hsvToHex({ h, s, v }: Hsv): string {
  const channel = (n: number) => {
    const k = (n + h / 60) % 6
    return v - v * s * Math.max(0, Math.min(k, 4 - k, 1))
  }
  return rgbToHex([channel(5), channel(3), channel(1)])
}
