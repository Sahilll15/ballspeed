import { existsSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Page } from '@playwright/test'

export const FIXTURE_DIR = join(tmpdir(), 'ballspeed-e2e')

export interface Truth {
  release_speed_ms: number
  spec: { width: number; height: number }
  calibration: { label: string; image: [number, number] }[]
}

export function clip(variant: string): { path: string; truth: Truth } {
  const path = join(FIXTURE_DIR, `delivery-${variant}.mp4`)
  if (!existsSync(path)) throw new Error(`missing fixture ${path}; global setup did not run`)
  const truth = JSON.parse(readFileSync(path.replace('.mp4', '.truth.json'), 'utf8')) as Truth
  return { path, truth }
}

/** Screen position of a video pixel on the frame canvas. */
export async function canvasPoint(page: Page, truth: Truth, u: number, v: number) {
  const box = await page.getByLabel('Video frame').boundingBox()
  if (!box) throw new Error('frame canvas not visible')
  return { x: box.x + (u / truth.spec.width) * box.width, y: box.y + (v / truth.spec.height) * box.height }
}
