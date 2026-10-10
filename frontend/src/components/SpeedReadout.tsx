import { useEffect, useState } from 'react'
import type { SpeedResult } from '../api/types'

const METHOD: Record<SpeedResult['method'], string> = {
  track_fit: 'Tracked trajectory fit',
  two_point: 'Two clicked ball positions',
  frame_count: 'Frame count over 18.9 m',
}

function useCountUp(target: number, ms = 900) {
  const [v, setV] = useState(0)
  useEffect(() => {
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const k = Math.min((now - t0) / ms, 1)
      setV(target * (1 - Math.pow(1 - k, 3)))
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}

export function SpeedReadout({ result, hideWarnings = [] }: { result: SpeedResult; hideWarnings?: string[] }) {
  const warnings = result.warnings.filter((w) => !hideWarnings.includes(w))
  const headline = result.release_speed_kmh ?? result.avg_speed_kmh
  const shown = useCountUp(headline)
  return (
    <section className="readout" data-testid="speed-readout">
      <div className="readout-label">{result.release_speed_kmh !== null ? 'Release speed' : 'Average speed'}</div>
      <div className="readout-value">
        <span className="mono-num" data-testid="speed-value" data-kmh={headline.toFixed(1)}>
          {shown.toFixed(1)}
        </span>
        <span className="unit">km/h</span>
      </div>
      <div className="readout-err mono">± {result.error_estimate_kmh.toFixed(1)} km/h</div>
      <dl className="stats">
        {result.release_speed_kmh !== null && (
          <div>
            <dt>Average</dt>
            <dd className="mono">{result.avg_speed_kmh.toFixed(1)} km/h</dd>
          </div>
        )}
        <div>
          <dt>Release</dt>
          <dd className="mono">frame {result.release_frame}</dd>
        </div>
        <div>
          <dt>Bounce</dt>
          <dd className="mono">{result.bounce_frame !== null ? `frame ${result.bounce_frame}` : '-'}</dd>
        </div>
        <div>
          <dt>Capture</dt>
          <dd className="mono">{Math.round(result.fps)} fps</dd>
        </div>
      </dl>
      <p className="dim small">{METHOD[result.method]}</p>
      {warnings.length > 0 && (
        <ul className="warnings">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
