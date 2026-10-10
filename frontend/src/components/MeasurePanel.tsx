import type { JobStatus, Point2D } from '../api/types'

export type ManualMode = 'frame_count' | 'two_point'

export interface ManualMarks {
  release: number | null
  end: number | null
  releaseBall: Point2D | null
  endBall: Point2D | null
}

interface Props {
  tab: 'auto' | 'manual'
  onTab: (t: 'auto' | 'manual') => void
  frame: number
  job: JobStatus | null
  canMeasure: boolean
  onAnalyze: () => void
  releaseOverride: number | null
  onReleaseOverride: (f: number | null) => void
  manualMode: ManualMode
  onManualMode: (m: ManualMode) => void
  marks: ManualMarks
  onMark: (which: 'release' | 'end') => void
  onManualCompute: () => void
}

export function MeasurePanel(p: Props) {
  const running = p.job !== null && (p.job.state === 'queued' || p.job.state === 'running')
  const manualReady =
    p.marks.release !== null &&
    p.marks.end !== null &&
    (p.manualMode === 'frame_count' || (p.marks.releaseBall !== null && p.marks.endBall !== null))
  return (
    <section className="panel">
      <header>
        <h3>Measure</h3>
        <div className="tabs" role="tablist">
          {(['auto', 'manual'] as const).map((t) => (
            <button key={t} role="tab" aria-selected={p.tab === t} className={p.tab === t ? 'on' : ''} onClick={() => p.onTab(t)}>
              {t === 'auto' ? 'Automatic' : 'Manual'}
            </button>
          ))}
        </div>
      </header>

      {p.tab === 'auto' ? (
        <>
          <button className="btn primary wide" disabled={!p.canMeasure || running} onClick={p.onAnalyze} data-testid="measure">
            {running ? p.job?.stage || 'Working…' : 'Measure speed'}
          </button>
          {running && p.job && (
            <div className="progress" aria-label="Progress">
              <div style={{ width: `${Math.round(p.job.progress * 100)}%` }} />
            </div>
          )}
          <div className="row small">
            <span className="dim">Release frame</span>
            {p.releaseOverride === null ? (
              <button className="link" onClick={() => p.onReleaseOverride(p.frame)}>
                auto · set to current ({p.frame})
              </button>
            ) : (
              <button className="link" onClick={() => p.onReleaseOverride(null)}>
                {p.releaseOverride} · clear
              </button>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="seg">
            <button className={p.manualMode === 'two_point' ? 'on' : ''} onClick={() => p.onManualMode('two_point')}>
              Two clicks
            </button>
            <button className={p.manualMode === 'frame_count' ? 'on' : ''} onClick={() => p.onManualMode('frame_count')}>
              Frame count
            </button>
          </div>
          <p className="dim small">
            {p.manualMode === 'two_point'
              ? 'Step to the release frame, mark it, then click the ball. Repeat for the last frame before the bounce.'
              : 'Mark the release frame and the frame the ball reaches the far stumps.'}
          </p>
          <div className="mark-row">
            <button className="btn" onClick={() => p.onMark('release')}>
              Release {p.marks.release !== null ? `· ${p.marks.release}` : ''}
            </button>
            <button className="btn" onClick={() => p.onMark('end')}>
              End {p.marks.end !== null ? `· ${p.marks.end}` : ''}
            </button>
          </div>
          <button className="btn primary wide" disabled={!manualReady} onClick={p.onManualCompute}>
            Compute speed
          </button>
        </>
      )}
    </section>
  )
}
