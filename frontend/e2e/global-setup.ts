import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { FIXTURE_DIR } from './fixtures.ts'

export default function globalSetup() {
  mkdirSync(FIXTURE_DIR, { recursive: true })
  for (const variant of ['cfr', 'slowmo']) {
    const out = join(FIXTURE_DIR, `delivery-${variant}.mp4`)
    if (existsSync(out)) continue
    execFileSync('uv', ['run', '--project', '../backend', 'ballspeed-synth', out, '--variant', variant], {
      stdio: 'inherit',
    })
  }
}
