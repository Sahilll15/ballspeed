// Records a 1080x1920 screen capture of the app measuring a delivery, for a reel.
// Usage: node scripts/record-demo.mjs <clip.mp4> <out.mp4> [--url http://localhost:5173]
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { chromium } from '@playwright/test'

const [, , clipPath, outPath, ...rest] = process.argv
if (!clipPath || !outPath) {
  console.error('usage: node scripts/record-demo.mjs <clip.mp4> <out.mp4> [--url URL]')
  process.exit(2)
}
const url = rest[rest.indexOf('--url') + 1] && rest.includes('--url') ? rest[rest.indexOf('--url') + 1] : 'http://localhost:5173'
const truth = JSON.parse(readFileSync(clipPath.replace(/\.mp4$/, '.truth.json'), 'utf8'))

const VIEW = { width: 432, height: 768 }
const SCALE = 2.5
const OUT_FPS = 30

const CURSOR = `
  addEventListener('DOMContentLoaded', () => {
    const c = document.createElement('div')
    c.id = '__cursor'
    c.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
      'background:rgba(255,255,255,.92);box-shadow:0 0 0 2px rgba(0,0,0,.55),0 4px 14px rgba(0,0,0,.4);' +
      'pointer-events:none;z-index:99999;transition:transform .12s ease;transform:translate(-100px,-100px)'
    document.body.appendChild(c)
    let x = -100, y = -100
    addEventListener('mousemove', (e) => { x = e.clientX; y = e.clientY; c.style.transform = 'translate(' + x + 'px,' + y + 'px)' }, true)
    addEventListener('mousedown', () => {
      c.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(.7)'
      const r = document.createElement('div')
      r.style.cssText = 'position:fixed;left:' + x + 'px;top:' + y + 'px;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;' +
        'border:2px solid #d4ff3a;pointer-events:none;z-index:99998;transition:all .45s ease-out;opacity:1'
      document.body.appendChild(r)
      requestAnimationFrame(() => { r.style.transform = 'scale(3.2)'; r.style.opacity = '0' })
      setTimeout(() => r.remove(), 500)
    }, true)
    addEventListener('mouseup', () => { c.style.transform = 'translate(' + x + 'px,' + y + 'px)' }, true)
  })`

const framesDir = mkdtempSync(join(tmpdir(), 'ballspeed-rec-'))
const frames = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: VIEW, deviceScaleFactor: SCALE })
await page.addInitScript(CURSOR)
const cdp = await page.context().newCDPSession(page)
cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
  const file = join(framesDir, `${String(frames.length).padStart(5, '0')}.jpg`)
  writeFileSync(file, Buffer.from(data, 'base64'))
  frames.push({ file, t: metadata.timestamp })
  await cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {})
})

let mouse = { x: VIEW.width / 2, y: VIEW.height * 0.8 }
const pause = (ms) => page.waitForTimeout(ms)
async function glide(x, y, ms = 650) {
  const steps = Math.max(Math.round(ms / 16), 2)
  for (let i = 1; i <= steps; i++) {
    const k = i / steps
    const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2
    await page.mouse.move(mouse.x + (x - mouse.x) * e, mouse.y + (y - mouse.y) * e)
    await pause(16)
  }
  mouse = { x, y }
}
async function clickAt(x, y, ms) {
  await glide(x, y, ms)
  await pause(120)
  await page.mouse.down()
  await pause(90)
  await page.mouse.up()
}
async function clickEl(locator, ms) {
  await locator.scrollIntoViewIfNeeded()
  const b = await locator.boundingBox()
  await clickAt(b.x + b.width / 2, b.y + b.height / 2, ms)
}
async function scrollTo(y, ms = 700) {
  await page.evaluate(([top, dur]) => {
    const start = scrollY, t0 = performance.now()
    return new Promise((done) => {
      const step = (now) => {
        const k = Math.min((now - t0) / dur, 1)
        scrollTo(0, start + (top - start) * (1 - Math.pow(1 - k, 3)))
        k < 1 ? requestAnimationFrame(step) : done()
      }
      requestAnimationFrame(step)
    })
  }, [y, ms])
}

await page.goto(url)
await page.mouse.move(mouse.x, mouse.y)
await cdp.send('Page.startScreencast', {
  format: 'jpeg', quality: 92, maxWidth: VIEW.width * SCALE, maxHeight: VIEW.height * SCALE, everyNthFrame: 1,
})
await pause(1500)

// Upload: point at the drop zone, then hand the file to the hidden input.
const drop = page.locator('.dropzone')
await clickEl(drop, 800).catch(() => {})
await page.getByTestId('file-input').setInputFiles(clipPath)
const canvas = page.getByLabel('Video frame')
await canvas.waitFor({ timeout: 60_000 })
await page.waitForFunction(() => !document.querySelector('.load-bar'), null, { timeout: 60_000 })
await pause(900)

// Show the slow-mo footage by playing it once.
await clickEl(page.getByRole('button', { name: 'Play' }), 600)
await page.waitForFunction(() => document.querySelector('[aria-label="Play"]'), null, { timeout: 20_000 })
await pause(500)

// Calibrate: hover near each stump point so the loupe shows, then click it.
const box = await canvas.boundingBox()
const toScreen = ([u, v]) => ({ x: box.x + (u / truth.spec.width) * box.width, y: box.y + (v / truth.spec.height) * box.height })
for (const point of truth.calibration) {
  const p = toScreen(point.image)
  await glide(p.x + 18, p.y - 14, 700)
  await pause(350)
  await clickAt(p.x, p.y, 300)
  await pause(450)
}
await page.getByTestId('calibrated').waitFor()
await pause(800)

await clickEl(page.getByTestId('measure'), 800)
await page.getByTestId('speed-value').waitFor({ timeout: 90_000 })
await scrollTo(0, 600)
await glide(VIEW.width - 30, VIEW.height - 40, 500)
await page.waitForFunction(() => document.querySelector('[aria-label="Play"]'), null, { timeout: 30_000 })
await pause(1200)
const readout = await page.getByTestId('speed-readout').boundingBox()
await scrollTo(Math.max(readout.y + (await page.evaluate(() => scrollY)) - 90, 0), 900)
await pause(3500)

await cdp.send('Page.stopScreencast')
await browser.close()

// Hold each captured frame until the next one, then resample to a constant frame rate.
const list = frames.map((f, i) => {
  const dur = i + 1 < frames.length ? Math.max(frames[i + 1].t - f.t, 0.001) : 0.5
  return `file '${f.file}'\nduration ${dur.toFixed(4)}`
})
list.push(`file '${frames.at(-1).file}'`)
const listFile = join(framesDir, 'frames.txt')
writeFileSync(listFile, list.join('\n'))
mkdirSync(join(outPath, '..'), { recursive: true })
execFileSync('ffmpeg', [
  '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listFile,
  '-vf', `scale=1080:1920:flags=lanczos,fps=${OUT_FPS}`, '-c:v', 'libx264', '-preset', 'slow',
  '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', outPath,
], { stdio: 'inherit' })
console.log(`${outPath}: ${frames.length} captured frames, ${(frames.at(-1).t - frames[0].t).toFixed(1)} s`)
