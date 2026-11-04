// A label that appears and disappears in small tiles, echoing how paintings dissolve as the web grows.

const CELL = 3 // px per tile, in screen pixels
const FONT = '500 15px system-ui, -apple-system, sans-serif'
const PAD_X = 14
const HEIGHT = 34

export type DissolveSprite = {
  image: HTMLCanvasElement
  width: number
  height: number
  ratio: number
  /** One entry per tile: its position and the 0–1 moment it changes. */
  cells: { x: number; y: number; at: number }[]
}

export function makeDissolveSprite(text: string, background: string, color: string, random = Math.random): DissolveSprite | null {
  const ratio = window.devicePixelRatio || 1
  const image = document.createElement('canvas')
  const ctx = image.getContext('2d')
  if (!ctx) return null
  ctx.font = FONT
  const width = Math.ceil(ctx.measureText(text).width) + 2 * PAD_X
  image.width = width * ratio
  image.height = HEIGHT * ratio
  ctx.scale(ratio, ratio)
  ctx.font = FONT // resizing the canvas reset it
  ctx.beginPath()
  ctx.roundRect(0, 0, width, HEIGHT, HEIGHT / 2)
  ctx.fillStyle = background
  ctx.fill()
  ctx.fillStyle = color
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'center'
  ctx.fillText(text, width / 2, HEIGHT / 2 + 1)
  const cells = []
  for (let y = 0; y < HEIGHT; y += CELL) {
    for (let x = 0; x < width; x += CELL) cells.push({ x, y, at: random() })
  }
  return { image, width, height: HEIGHT, ratio, cells }
}

/**
 * Draws the sprite centered on (x, y) in map coordinates, at a constant size on screen.
 * `shown` runs 0–1 as tiles arrive, and `gone` runs 0–1 as they leave.
 */
export function drawDissolve(ctx: CanvasRenderingContext2D, sprite: DissolveSprite, x: number, y: number,
                             scale: number, shown: number, gone: number) {
  const { image, width, height, ratio, cells } = sprite
  const left = x - width / 2 / scale
  const top = y - height / 2 / scale
  if (shown >= 1 && gone <= 0) {
    ctx.drawImage(image, left, top, width / scale, height / scale)
    return
  }
  const size = CELL / scale
  for (const cell of cells) {
    if (cell.at > shown || cell.at < gone) continue
    ctx.drawImage(image, cell.x * ratio, cell.y * ratio, CELL * ratio, CELL * ratio,
                  left + cell.x / scale, top + cell.y / scale, size, size)
  }
}
