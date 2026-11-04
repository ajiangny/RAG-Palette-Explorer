// Editing and sharing the user's palette. It lives in the URL, so every query is a link.

import { hexToOklch, isHex, normalizeHex, oklchToHex } from './color.ts'

export const MAX_DOTS = 5

export function parsePalette(param: string | null): string[] | null {
  if (!param) return null
  const hexes = param.split('-').filter(isHex).map(normalizeHex).slice(0, MAX_DOTS)
  return hexes.length ? hexes : null
}

export const formatPalette = (hexes: string[]) => hexes.map((h) => h.replace('#', '')).join('-')

/** Rotates every hue by one amount, keeping each color's lightness and chroma. */
export function shuffleHues(hexes: string[], random = Math.random): string[] {
  const turn = 40 + random() * 280
  return hexes.map((hex) => {
    const c = hexToOklch(hex)
    return oklchToHex({ ...c, h: (c.h + turn) % 360 })
  })
}

export type UrlState = { center: number | null; palette: string[] | null }

export function readUrl(search: string): UrlState {
  const params = new URLSearchParams(search)
  const center = Number(params.get('c'))
  return { center: Number.isInteger(center) && center > 0 ? center : null, palette: parsePalette(params.get('p')) }
}

export function writeUrl({ center, palette }: UrlState): string {
  const parts = []
  if (center != null) parts.push(`c=${center}`)
  if (palette?.length) parts.push(`p=${formatPalette(palette)}`)
  return parts.length ? `?${parts.join('&')}` : ''
}
