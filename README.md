# Ballspeed

Upload a video of a bowler and get the ball's speed in km/h. A FastAPI backend runs a computer vision pipeline over the frames, and a React frontend handles calibration, scrubbing and the result overlay.

## Setup

You need Python 3.11 with [uv](https://docs.astral.sh/uv/), Node 22, and ffmpeg (`brew install ffmpeg`).

```bash
cd backend && uv sync
uv run uvicorn ballspeed.main:app --port 8000

cd frontend && npm install
npm run dev            # http://localhost:5173, proxies /api to :8000
```

To try it without footage, render a synthetic 140 km/h delivery and upload it:

```bash
cd backend && uv run ballspeed-synth /tmp/delivery.mp4 --variant slowmo
```

## Using it

1. Upload an mp4 or mov clip.
2. Click the base and top of the bowler's stumps, then the base and top of the batter's stumps. A loupe helps you place each click. The app works out a pixel to metre mapping for the vertical plane the ball flies in.
3. Press **Measure speed**. The app tracks the ball, finds release and bounce, and fits the flight.
4. If tracking fails, switch to **Manual**. Two-click mode uses the calibration and two clicked ball positions. Frame-count mode needs no calibration: it divides 18.9 m by the time between two marked frames.

## Filming tips

- Shoot 240 fps slow motion. At 30 fps one frame of timing error is worth about 10 km/h. At 240 fps it is about 1.2 km/h.
- Use a tripod. Camera shake breaks the background subtraction.
- Film side-on, roughly level with the middle of the pitch, with both sets of stumps in frame. The calibration assumes this view.
- Behind-the-bowler footage is not supported for automatic speed. The ball moves mostly towards the camera, and one camera cannot measure depth well.
- Use the 1x lens. The ultra-wide lens bends straight lines, and the calibration assumes it doesn't.
- Trim the clip to the delivery before uploading. The limit is 3000 frames.
- If you share a slow-motion clip from a phone, it may come out re-timed to play at 30 fps. Android records the real rate in metadata and the app reads it. For other clips, set the capture fps by hand, or every speed will read about 8 times too low.

## How accurate is it

On synthetic test footage it recovers release speed within 1%. Real footage will do worse, for these reasons:

- The calibration maps the plane through both middle stumps. A ball that drifts towards off or leg is slightly off that plane, so its distances come out a little wrong.
- Release is found from the ball track. For the first few frames after release the ball hides against the bowler's arm, so the detected release can be a few frames late. That costs roughly 0.2 km/h per frame at 240 fps, and the error range includes it. Installing MediaPipe (`uv add mediapipe`) refines release using the bowler's wrist.
- Frame-count mode averages the whole flight, bounce included, so it reads 10 to 15% below a radar gun.
- The classical detector expects a bright ball against a darker background. A red ball against a brown pitch, or a cluttered background, may need a trained detector. The `BallDetector` interface accepts a YOLO model through `BALLSPEED_DETECTOR=yolo` and `BALLSPEED_YOLO_WEIGHTS`.
- The ± figure is a 95% range from the fit, the calibration and release timing. It does not cover a bad calibration click.

## Tests

```bash
cd backend && uv run pytest              # renders synthetic clips, checks speed within 2%
cd frontend && npm run test:e2e          # drives the real UI with Playwright
```

## Deploying

The root `Dockerfile` builds the frontend and serves it from FastAPI, with ffmpeg installed, so the whole app runs as one container. `render.yaml` describes it as a Render web service. The app keeps uploads on local disk between requests, so run a single instance.

## Recording a demo

`frontend/scripts/record-demo.mjs` drives the app in a 1080x1920 portrait window and saves an mp4, for reels. Run it with both servers up:

```bash
cd frontend && node scripts/record-demo.mjs /tmp/delivery.mp4 ../recordings/demo.mp4
```
