import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, describeError } from './api/client'
import type { Calibration, JobStatus, Point2D, SpeedResult, VideoMeta } from './api/types'
import { CALIB_TARGETS } from './calibration'
import { CalibrationPanel } from './components/CalibrationPanel'
import { FrameView, type Marker } from './components/FrameView'
import { type ManualMarks, type ManualMode, MeasurePanel } from './components/MeasurePanel'
import { MetaBar } from './components/MetaBar'
import { Scrubber } from './components/Scrubber'
import { SpeedReadout } from './components/SpeedReadout'
import { Upload } from './components/Upload'
import { useFrames } from './hooks/useFrames'

const PLAYBACK_FPS = 30
const POLL_MS = 250
const STEPS = ['Upload', 'Calibrate', 'Measure', 'Result'] as const
const NO_MARKS: ManualMarks = { release: null, end: null, releaseBall: null, endBall: null }

type ErrorView = { message: string; hint: string }

export default function App() {
  const [meta, setMeta] = useState<VideoMeta | null>(null)
  const [times, setTimes] = useState<number[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<ErrorView | null>(null)
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [stopAt, setStopAt] = useState<number | null>(null)

  const [clicks, setClicks] = useState<Point2D[]>([])
  const [calibration, setCalibration] = useState<Calibration | null>(null)
  const [savingCal, setSavingCal] = useState(false)

  const [tab, setTab] = useState<'auto' | 'manual'>('auto')
  const [job, setJob] = useState<JobStatus | null>(null)
  const [result, setResult] = useState<SpeedResult | null>(null)
  const [releaseOverride, setReleaseOverride] = useState<number | null>(null)
  const [manualMode, setManualMode] = useState<ManualMode>('two_point')
  const [marks, setMarks] = useState<ManualMarks>(NO_MARKS)
  const [pickingBall, setPickingBall] = useState<'release' | 'end' | null>(null)

  const frames = useFrames(meta?.id ?? null, meta?.frame_count ?? 0)
  const count = meta?.frame_count ?? 0

  const fail = (e: unknown) => setError(describeError(e))

  const reset = () => {
    setMeta(null)
    setTimes([])
    setFrame(0)
    setPlaying(false)
    setClicks([])
    setCalibration(null)
    setJob(null)
    setResult(null)
    setReleaseOverride(null)
    setMarks(NO_MARKS)
    setPickingBall(null)
    setError(null)
  }

  const onFile = async (file: File) => {
    reset()
    setUploading(true)
    try {
      const m = await api.upload(file)
      setMeta(m)
      setTimes((await api.timestamps(m.id)).t_s)
    } catch (e) {
      fail(e)
    } finally {
      setUploading(false)
    }
  }

  const onCaptureFps = async (fps: number) => {
    if (!meta) return
    try {
      const m = await api.patch(meta.id, { capture_fps: fps })
      setMeta(m)
      setTimes((await api.timestamps(m.id)).t_s)
      setResult(null)
    } catch (e) {
      fail(e)
    }
  }

  const onPick = async (p: Point2D) => {
    if (!meta) return
    if (clicks.length < CALIB_TARGETS.length) {
      const next = [...clicks, p]
      setClicks(next)
      if (next.length === CALIB_TARGETS.length) {
        setSavingCal(true)
        try {
          const points = CALIB_TARGETS.map((t, i) => ({ label: t.label, image: next[i]!, world: t.world }))
          setCalibration(await api.calibrate(meta.id, { mode: 'vertical_plane', points }))
        } catch (e) {
          fail(e)
          setClicks([])
        } finally {
          setSavingCal(false)
        }
      }
      return
    }
    if (pickingBall) {
      setMarks((m) => (pickingBall === 'release' ? { ...m, releaseBall: p } : { ...m, endBall: p }))
      setPickingBall(null)
    }
  }

  const play = useCallback((from: number, to: number | null) => {
    setFrame(from)
    setStopAt(to)
    setPlaying(true)
  }, [])

  useEffect(() => {
    if (!playing || count === 0) return
    const id = window.setInterval(() => {
      setFrame((f) => {
        const end = stopAt ?? count - 1
        if (f >= end) {
          setPlaying(false)
          return f
        }
        return f + 1
      })
    }, 1000 / PLAYBACK_FPS)
    return () => window.clearInterval(id)
  }, [playing, stopAt, count])

  const onAnalyze = async () => {
    if (!meta) return
    setResult(null)
    setError(null)
    try {
      let j = await api.analyze(meta.id, releaseOverride !== null ? { release_frame_override: releaseOverride } : {})
      setJob(j)
      while (j.state === 'queued' || j.state === 'running') {
        await new Promise((r) => setTimeout(r, POLL_MS))
        j = await api.job(j.id)
        setJob(j)
      }
      if (j.state === 'failed' && j.error) setError({ message: j.error.message, hint: j.error.hint })
      if (j.result) {
        setResult(j.result)
        play(Math.max(j.result.release_frame - 10, 0), Math.min(j.result.end_frame + 20, count - 1))
      }
    } catch (e) {
      fail(e)
    }
  }

  const onMark = (which: 'release' | 'end') => {
    setMarks((m) => (which === 'release' ? { ...m, release: frame, releaseBall: null } : { ...m, end: frame, endBall: null }))
    if (manualMode === 'two_point') setPickingBall(which)
  }

  const onManualCompute = async () => {
    if (!meta || marks.release === null || marks.end === null) return
    setError(null)
    try {
      const two = manualMode === 'two_point' && marks.releaseBall && marks.endBall
      const r = await api.manual(meta.id, {
        mode: manualMode,
        release_frame: marks.release,
        end_frame: marks.end,
        ...(two ? { release_ball: marks.releaseBall!, end_ball: marks.endBall! } : {}),
      })
      setResult(r)
      play(marks.release, marks.end)
    } catch (e) {
      fail(e)
    }
  }

  const markers = useMemo<Marker[]>(() => {
    const out: Marker[] = (result ? [] : clicks).map((c, i) => ({
      at: c,
      label: CALIB_TARGETS[i]!.name.replace("'s stumps, ", ' '),
      tone: 'calib',
    }))
    if (result) {
      const at = (f: number | null) => result.track.find((p) => p.frame === f)
      const r = at(result.release_frame)
      const b = at(result.bounce_frame)
      if (r && frame >= result.release_frame) out.push({ at: { x: r.x_px, y: r.y_px }, label: 'Release', tone: 'release' })
      if (b && result.bounce_frame !== null && frame >= result.bounce_frame)
        out.push({ at: { x: b.x_px, y: b.y_px }, label: 'Bounce', tone: 'bounce' })
    }
    if (marks.releaseBall && frame === marks.release) out.push({ at: marks.releaseBall, label: 'Release ball', tone: 'manual' })
    if (marks.endBall && frame === marks.end) out.push({ at: marks.endBall, label: 'End ball', tone: 'manual' })
    return out
  }, [clicks, result, frame, marks])

  const picking = meta !== null && (clicks.length < CALIB_TARGETS.length || pickingBall !== null)
  const step = !meta ? 0 : !calibration ? 1 : !result ? 2 : 3
  const loadingPct = count ? Math.round((frames.loaded / count) * 100) : 0

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-ball" aria-hidden />
          Ballspeed
        </div>
        <nav className="step-nav" aria-label="Progress">
          {STEPS.map((label, i) => (
            <span key={label} className={i === step ? 'on' : i < step ? 'done' : ''}>
              {label}
            </span>
          ))}
        </nav>
        {meta ? (
          <button className="btn ghost" onClick={reset}>
            New clip
          </button>
        ) : (
          <span className="status-chip">
            <i /> Ready
          </span>
        )}
      </header>

      {error && (
        <div className="error" role="alert">
          <strong>{error.message}</strong>
          {error.hint && <span> {error.hint}</span>}
          <button className="link" onClick={() => setError(null)} aria-label="Dismiss">
            dismiss
          </button>
        </div>
      )}

      {!meta ? (
        <Upload busy={uploading} onFile={onFile} />
      ) : (
        <main className="workspace">
          <div className="viewer">
            <div className="frame-wrap">
              <FrameView
                image={frames.get(frame)}
                width={meta.width}
                height={meta.height}
                frame={frame}
                markers={markers}
                track={result?.track ?? []}
                trackFrom={result ? result.release_frame : null}
                picking={picking}
                onPick={onPick}
              />
              <div className="glass tag">
                <span className="live-dot" />
                <span className="mono">{Math.round(meta.capture_fps)} FPS</span>
                <span className="dim">{meta.filename}</span>
              </div>
              {result && (
                <div className="glass stat" data-testid="overlay-speed">
                  <span className="stat-label">{result.release_speed_kmh !== null ? 'Release' : 'Average'}</span>
                  <span className="stat-num">{(result.release_speed_kmh ?? result.avg_speed_kmh).toFixed(1)}</span>
                  <span className="stat-unit">km/h</span>
                </div>
              )}
              {picking && (
                <div className="hint-pill">
                  {clicks.length < CALIB_TARGETS.length
                    ? `Click: ${CALIB_TARGETS[clicks.length]!.name}`
                    : `Click the ball (${pickingBall} frame)`}
                </div>
              )}
              {loadingPct < 100 && <div className="load-bar" style={{ width: `${loadingPct}%` }} />}
            </div>
            <Scrubber
              frame={frame}
              count={count}
              timeS={times[frame]}
              playing={playing}
              onFrame={(f) => {
                setPlaying(false)
                setFrame(f)
              }}
              onTogglePlay={() => (playing ? setPlaying(false) : play(frame >= count - 1 ? 0 : frame, null))}
            />
            <MetaBar key={meta.capture_fps} meta={meta} onCaptureFps={onCaptureFps} />
            {meta.warnings.length > 0 && (
              <ul className="warnings">
                {meta.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </div>

          <aside className="side">
            {result && <SpeedReadout key={`${result.method}-${result.release_frame}-${result.avg_speed_kmh}`} result={result} hideWarnings={meta.warnings} />}
            <CalibrationPanel
              clicks={clicks}
              calibration={calibration}
              saving={savingCal}
              onReset={() => {
                setClicks([])
                setCalibration(null)
              }}
            />
            <MeasurePanel
              tab={tab}
              onTab={setTab}
              frame={frame}
              job={job}
              canMeasure={calibration !== null}
              onAnalyze={onAnalyze}
              releaseOverride={releaseOverride}
              onReleaseOverride={setReleaseOverride}
              manualMode={manualMode}
              onManualMode={setManualMode}
              marks={marks}
              onMark={onMark}
              onManualCompute={onManualCompute}
            />
          </aside>
        </main>
      )}
    </div>
  )
}
