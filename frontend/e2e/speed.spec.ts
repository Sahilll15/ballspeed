import { expect, test } from '@playwright/test'
import { canvasPoint, clip } from './fixtures.ts'

for (const variant of ['cfr', 'slowmo']) {
  test(`measures a 140 km/h delivery (${variant})`, async ({ page }) => {
    const { path, truth } = clip(variant)
    await page.goto('/')
    await page.getByTestId('file-input').setInputFiles(path)
    await expect(page.getByLabel('Video frame')).toBeVisible()
    await expect(page.getByTestId('capture-fps')).toHaveText('240 fps')

    for (const point of truth.calibration) {
      const p = await canvasPoint(page, truth, point.image[0], point.image[1])
      await page.mouse.click(p.x, p.y)
    }
    await expect(page.getByTestId('calibrated')).toBeVisible()

    await page.getByTestId('measure').click()
    const value = page.getByTestId('speed-value')
    await expect(value).toBeVisible({ timeout: 60_000 })
    const kmh = Number(await value.getAttribute('data-kmh'))
    const trueKmh = truth.release_speed_ms * 3.6
    expect(Math.abs(kmh - trueKmh) / trueKmh).toBeLessThan(0.02)
    await expect(page.getByTestId('overlay-speed')).toContainText(kmh.toFixed(1))
  })
}

test('explains a bad upload', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('file-input').setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('not a video'),
  })
  await expect(page.getByRole('alert')).toContainText('not supported')
})
