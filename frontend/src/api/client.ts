import type {
  AnalyzeRequest,
  ApiErrorBody,
  Calibration,
  CalibrationRequest,
  JobStatus,
  ManualSpeedRequest,
  SpeedResult,
  Timestamps,
  VideoMeta,
  VideoPatch,
} from './types'

export class ApiError extends Error {
  readonly code: string
  readonly hint: string

  constructor(body: ApiErrorBody) {
    super(body.message)
    this.code = body.code
    this.hint = body.hint
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null
    throw new ApiError(body ?? { code: 'HTTP_' + res.status, message: res.statusText, hint: '' })
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

function json<T>(method: string, path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export const api = {
  upload(file: File): Promise<VideoMeta> {
    const form = new FormData()
    form.append('file', file)
    return request('/api/videos', { method: 'POST', body: form })
  },
  patch: (id: string, patch: VideoPatch) => json<VideoMeta>('PATCH', `/api/videos/${id}`, patch),
  timestamps: (id: string) => request<Timestamps>(`/api/videos/${id}/timestamps`),
  frameUrl: (id: string, i: number) => `/api/videos/${id}/frames/${i}.jpg`,
  calibrate: (id: string, req: CalibrationRequest) =>
    json<Calibration>('PUT', `/api/videos/${id}/calibration`, req),
  manual: (id: string, req: ManualSpeedRequest) =>
    json<SpeedResult>('POST', `/api/videos/${id}/speed/manual`, req),
  analyze: (id: string, req: AnalyzeRequest) =>
    json<JobStatus>('POST', `/api/videos/${id}/analyze`, req),
  job: (jobId: string) => request<JobStatus>(`/api/jobs/${jobId}`),
}

export function describeError(e: unknown): { message: string; hint: string } {
  if (e instanceof ApiError) return { message: e.message, hint: e.hint }
  if (e instanceof Error) return { message: e.message, hint: '' }
  return { message: String(e), hint: '' }
}
