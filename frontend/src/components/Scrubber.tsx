import { useEffect } from 'react'

interface Props {
  frame: number
  count: number
  timeS: number | undefined
  playing: boolean
  onFrame: (f: number) => void
  onTogglePlay: () => void
}

export function Scrubber({ frame, count, timeS, playing, onFrame, onTogglePlay }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement && e.target.type !== 'range') return
      if (e.key === 'ArrowRight') onFrame(Math.min(frame + (e.shiftKey ? 10 : 1), count - 1))
      else if (e.key === 'ArrowLeft') onFrame(Math.max(frame - (e.shiftKey ? 10 : 1), 0))
      else if (e.key === ' ') onTogglePlay()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [frame, count, onFrame, onTogglePlay])

  return (
    <div className="scrubber">
      <button className="icon-btn" onClick={() => onFrame(Math.max(frame - 1, 0))} aria-label="Previous frame">
        ‹
      </button>
      <button className="icon-btn play" onClick={onTogglePlay} aria-label={playing ? 'Pause' : 'Play'}>
        {playing ? '❚❚' : '▶'}
      </button>
      <button className="icon-btn" onClick={() => onFrame(Math.min(frame + 1, count - 1))} aria-label="Next frame">
        ›
      </button>
      <input
        type="range"
        min={0}
        max={count - 1}
        value={frame}
        onChange={(e) => onFrame(Number(e.target.value))}
        aria-label="Frame"
      />
      <span className="mono frame-label">
        {String(frame).padStart(3, '0')}/{count - 1}
        <span className="dim"> · {timeS !== undefined ? timeS.toFixed(3) : '-'} s</span>
      </span>
    </div>
  )
}
