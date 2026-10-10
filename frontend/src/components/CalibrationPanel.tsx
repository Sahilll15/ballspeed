import type { Calibration, Point2D } from '../api/types'
import { CALIB_TARGETS } from '../calibration'


interface Props {
  clicks: Point2D[]
  calibration: Calibration | null
  saving: boolean
  onReset: () => void
}

export function CalibrationPanel({ clicks, calibration, saving, onReset }: Props) {
  const next = clicks.length
  if (calibration)
    return (
      <section className="panel calib-done" data-testid="calibrated">
        <span className="tick">✓</span>
        <div style={{ flex: 1 }}>
          <h3>Pitch calibrated</h3>
          <p className="dim small">Reprojection error {calibration.reprojection_error_px.toFixed(2)} px</p>
        </div>
        <button className="link" onClick={onReset}>
          redo
        </button>
      </section>
    )
  return (
    <section className="panel">
      <header>
        <h3>Calibrate the pitch</h3>
        {clicks.length > 0 && (
          <button className="link" onClick={onReset}>
            reset
          </button>
        )}
      </header>
      <p className="dim small">Click each point on the frame. The ball flies in the plane of the stumps.</p>
      <ol className="steps">
        {CALIB_TARGETS.map((t, i) => (
          <li key={t.label} className={i < next ? 'done' : i === next ? 'current' : ''}>
            <span className="dot" />
            {t.name}
          </li>
        ))}
      </ol>
      {saving && <p className="dim small">Computing homography…</p>}
    </section>
  )
}
