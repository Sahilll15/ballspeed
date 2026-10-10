import { useState } from 'react'
import type { VideoMeta } from '../api/types'

interface Props {
  meta: VideoMeta
  onCaptureFps: (fps: number) => void
}

export function MetaBar({ meta, onCaptureFps }: Props) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(String(Math.round(meta.capture_fps)))

  return (
    <div className="meta-bar">
      <span className="chip strong mono" data-testid="capture-fps">
        {Math.round(meta.capture_fps)} fps
      </span>
      {meta.slowmo_detected && <span className="chip accent">slow-mo</span>}
      {meta.is_vfr && <span className="chip">variable frame rate</span>}
      <span className="chip dim mono">
        {meta.width}×{meta.height} · {meta.frame_count} frames · {meta.duration_s.toFixed(2)} s
      </span>
      {editing ? (
        <form
          className="fps-form"
          onSubmit={(e) => {
            e.preventDefault()
            const n = Number(value)
            if (n > 0) onCaptureFps(n)
            setEditing(false)
          }}
        >
          <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" autoFocus />
          <button className="btn small">Set</button>
        </form>
      ) : (
        <button className="link" onClick={() => setEditing(true)}>
          capture fps
        </button>
      )}
    </div>
  )
}
