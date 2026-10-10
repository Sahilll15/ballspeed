import { useRef, useState } from 'react'

interface Props {
  busy: boolean
  onFile: (f: File) => void
}

export function Upload({ busy, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  return (
    <div
      className={`dropzone${over ? ' over' : ''}${busy ? ' busy' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const f = e.dataTransfer.files[0]
        if (f && !busy) onFile(f)
      }}
      onClick={() => !busy && input.current?.click()}
      role="button"
      tabIndex={0}
    >
      <input
        ref={input}
        type="file"
        accept="video/mp4,video/quicktime,.mp4,.mov,.m4v"
        hidden
        data-testid="file-input"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          e.target.value = ''
        }}
      />
      <div className="ball" aria-hidden />
      <h2>{busy ? 'Reading frames…' : 'Drop a delivery clip'}</h2>
      <p className="dim">MP4 or MOV. 240 fps slow motion on a tripod, filmed side-on.</p>
    </div>
  )
}
