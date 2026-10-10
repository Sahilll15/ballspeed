// Mirrors backend/src/ballspeed/models.py. Keep the two in sync.

export interface Point2D {
  x: number
  y: number
}

export interface FrameRange {
  start: number
  end: number
}

export type CaptureFpsSource = 'container' | 'metadata' | 'user'

export interface VideoMeta {
  id: string
  filename: string
  width: number
  height: number
  frame_count: number
  duration_s: number
  nominal_fps: number
  measured_fps: number
  capture_fps: number
  capture_fps_source: CaptureFpsSource
  is_vfr: boolean
  slowmo_detected: boolean
  trim: FrameRange | null
  calibrated: boolean
  warnings: string[]
}

export interface VideoPatch {
  capture_fps?: number
  trim?: FrameRange
}

export interface Timestamps {
  video_id: string
  t_s: number[]
}

export type CalibrationMode = 'vertical_plane' | 'ground_plane'

export interface CalibrationPoint {
  label: string
  image: Point2D
  world: Point2D
}

export interface CalibrationRequest {
  mode: CalibrationMode
  points: CalibrationPoint[]
}

export interface Calibration extends CalibrationRequest {
  homography: number[][]
  reprojection_error_px: number
}

export interface ManualSpeedRequest {
  mode: 'frame_count' | 'two_point'
  release_frame: number
  end_frame: number
  distance_m?: number
  release_ball?: Point2D
  end_ball?: Point2D
}

export interface AnalyzeRequest {
  release_frame_override?: number
}

export interface TrackPoint {
  frame: number
  t_s: number
  x_px: number
  y_px: number
  x_m: number | null
  z_m: number | null
  source: 'detected' | 'predicted' | 'manual'
  confidence: number
}

export type SpeedMethod = 'frame_count' | 'two_point' | 'track_fit'

export interface SpeedResult {
  release_speed_kmh: number | null
  avg_speed_kmh: number
  error_estimate_kmh: number
  method: SpeedMethod
  fps: number
  release_frame: number
  bounce_frame: number | null
  end_frame: number
  track: TrackPoint[]
  warnings: string[]
}

export interface ApiErrorBody {
  code: string
  message: string
  hint: string
}

export type JobState = 'queued' | 'running' | 'done' | 'failed'

export interface JobStatus {
  id: string
  video_id: string
  state: JobState
  progress: number
  stage: string
  result: SpeedResult | null
  error: ApiErrorBody | null
}
