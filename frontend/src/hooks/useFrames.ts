import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

const CONCURRENCY = 6

/** Preloads every frame image so scrubbing and playback never wait on the network. */
export function useFrames(videoId: string | null, count: number) {
  const cache = useRef<HTMLImageElement[]>([])
  const [progress, setProgress] = useState<{ id: string | null; n: number }>({ id: null, n: 0 })

  useEffect(() => {
    cache.current = []
    if (!videoId || count === 0) return
    let cancelled = false
    let next = 0
    let done = 0
    const pump = () => {
      if (cancelled || next >= count) return
      const i = next++
      const img = new Image()
      img.decoding = 'async'
      img.onload = img.onerror = () => {
        if (cancelled) return
        cache.current[i] = img
        done++
        if (done % 8 === 0 || done === count) setProgress({ id: videoId, n: done })
        pump()
      }
      img.src = api.frameUrl(videoId, i)
    }
    for (let k = 0; k < CONCURRENCY; k++) pump()
    return () => {
      cancelled = true
    }
  }, [videoId, count])

  const loaded = progress.id === videoId ? progress.n : 0
  return { get: (i: number) => cache.current[i], loaded }
}
