import { useEffect, useRef, useState } from 'react'
import type { Point2D, TrackPoint } from '../api/types'

export interface Marker {
  at: Point2D
  label: string
  tone: 'calib' | 'release' | 'bounce' | 'manual'
}

interface Props {
  image: HTMLImageElement | undefined
  width: number
  height: number
  frame: number
  markers: Marker[]
  track: TrackPoint[]
  trackFrom: number | null
  picking: boolean
  onPick?: (p: Point2D) => void
}

const LOUPE_ZOOM = 5
const LOUPE_RADIUS = 70

const TONES: Record<Marker['tone'], string> = {
  calib: '#5ac8fa',
  release: '#d4ff3a',
  bounce: '#ff8a3d',
  manual: '#f472b6',
}

export function FrameView({ image, width, height, frame, markers, track, trackFrom, picking, onPick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [pointer, setPointer] = useState<Point2D | null>(null)
  const lastImage = useRef<HTMLImageElement | undefined>(undefined)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const cssW = canvas.clientWidth
    canvas.width = Math.round(cssW * dpr)
    canvas.height = Math.round((cssW * height) / width * dpr)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const s = canvas.width / width
    const img = image?.complete && image.naturalWidth ? image : lastImage.current
    if (img) {
      lastImage.current = img
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    } else {
      ctx.fillStyle = '#0b0f14'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
    }

    if (trackFrom !== null) {
      const shown = track.filter((p) => p.frame >= trackFrom && p.frame <= frame)
      ctx.lineWidth = 2.5 * dpr
      ctx.strokeStyle = 'rgba(212, 255, 58, 0.85)'
      ctx.shadowColor = 'rgba(212, 255, 58, 0.9)'
      ctx.shadowBlur = 8 * dpr
      ctx.beginPath()
      shown.forEach((p, k) => (k ? ctx.lineTo(p.x_px * s, p.y_px * s) : ctx.moveTo(p.x_px * s, p.y_px * s)))
      ctx.stroke()
      ctx.shadowBlur = 0
      const cur = shown.at(-1)
      if (cur && cur.frame === frame) {
        ctx.strokeStyle = '#d4ff3a'
        ctx.lineWidth = 2 * dpr
        ctx.beginPath()
        ctx.arc(cur.x_px * s, cur.y_px * s, 9 * dpr, 0, Math.PI * 2)
        ctx.stroke()
      }
    }

    ctx.font = `600 ${12 * dpr}px Inter, system-ui, sans-serif`
    for (const m of markers) {
      const x = m.at.x * s
      const y = m.at.y * s
      ctx.strokeStyle = TONES[m.tone]
      ctx.fillStyle = TONES[m.tone]
      ctx.lineWidth = 1.5 * dpr
      ctx.beginPath()
      ctx.moveTo(x - 7 * dpr, y)
      ctx.lineTo(x + 7 * dpr, y)
      ctx.moveTo(x, y - 7 * dpr)
      ctx.lineTo(x, y + 7 * dpr)
      ctx.stroke()
      const tw = ctx.measureText(m.label).width + 10 * dpr
      const lx = x + 8 * dpr + tw > canvas.width ? x - 8 * dpr - tw : x + 8 * dpr
      ctx.fillStyle = 'rgba(8, 11, 16, 0.78)'
      ctx.fillRect(lx, y - 22 * dpr, tw, 17 * dpr)
      ctx.fillStyle = TONES[m.tone]
      ctx.fillText(m.label, lx + 5 * dpr, y - 9 * dpr)
    }

    if (picking && pointer && img) {
      const r = LOUPE_RADIUS * dpr
      const px = pointer.x * s
      const cx = px < canvas.width / 2 ? canvas.width - r - 12 * dpr : r + 12 * dpr
      // Below the filename tag in the top-left corner.
      const cy = r + 52 * dpr
      const srcR = LOUPE_RADIUS / LOUPE_ZOOM
      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.clip()
      ctx.imageSmoothingEnabled = false
      ctx.drawImage(img, pointer.x - srcR, pointer.y - srcR, srcR * 2, srcR * 2, cx - r, cy - r, r * 2, r * 2)
      ctx.restore()
      ctx.strokeStyle = '#d4ff3a'
      ctx.lineWidth = 2 * dpr
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.moveTo(cx - 10 * dpr, cy)
      ctx.lineTo(cx + 10 * dpr, cy)
      ctx.moveTo(cx, cy - 10 * dpr)
      ctx.lineTo(cx, cy + 10 * dpr)
      ctx.stroke()
    }
  }, [image, width, height, frame, markers, track, trackFrom, picking, pointer])

  const toImage = (e: React.MouseEvent<HTMLCanvasElement>): Point2D => {
    const rect = e.currentTarget.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width) * width,
      y: ((e.clientY - rect.top) / rect.height) * height,
    }
  }

  return (
    <canvas
      ref={canvasRef}
      className={`frame-view${picking ? ' picking' : ''}`}
      style={{ aspectRatio: `${width} / ${height}` }}
      onPointerMove={(e) => picking && setPointer(toImage(e))}
      onPointerLeave={() => setPointer(null)}
      onClick={(e) => picking && onPick?.(toImage(e))}
      aria-label="Video frame"
    />
  )
}
