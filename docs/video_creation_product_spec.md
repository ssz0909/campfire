# Video Creation Product Specification

---

## 1. Mode A — AI Creative: User Flow

The user has a topic and wants the system to do all creative work.

1. **Create project:** User clicks "New Video", selects Mode A, enters a working title.
2. **Brief input:** User fills a structured brief form:
   - Topic / subject (required)
   - Target audience (required)
   - Tone: informative / promotional / emotional / humorous (required)
   - Target duration: 15s / 30s / 60s / 90s (required)
   - Brand guidelines: logo upload (optional), color preference (optional), forbidden words (optional)
   - Reference examples: URLs or uploaded videos (optional)
3. **Script generation:** System calls the LLM with the brief. The LLM returns a structured script containing: title, total duration, and an ordered list of shots.
4. **Script review:** User reviews the generated script. Each shot is displayed as a card: shot number, description, estimated duration, on-screen text. User can edit shot descriptions or delete shots. User approves the script to proceed.
5. **Shot generation:** Each approved shot is dispatched as a Celery task to the video provider. Shot cards display progress indicators.
6. **Synthesis:** Once all shots reach `COMPLETE`, the synthesis worker runs FFmpeg automatically.
7. **Preview and download:** User previews the assembled video in the browser. User can approve and download, or request a revision (which returns to Step 4 with the current script pre-filled).

---

## 2. Mode B — Reference-Inspired: User Flow

The user has a reference video they want to emulate stylistically.

1. **Create project:** User clicks "New Video", selects Mode B, enters a working title.
2. **Reference upload:** User uploads a reference video (max 200MB, MP4/MOV/AVI).
3. **Style extraction:** System sends the reference video to a vision model (or uses frame sampling with GPT-4V) to extract:
   - Pacing (cuts per minute)
   - Visual style descriptors (cinematic, flat, energetic, calm, etc.)
   - Color temperature (warm / cool / neutral)
   - Text overlay style (font weight, position, frequency)
   - Audio: music present? voice-over present?
4. **Brief input (condensed):** User provides topic, audience, and duration. Style fields are pre-filled from extraction; user can override.
5. **Continue as Mode A from Step 3:** The extracted style tokens are injected into the LLM prompt as style constraints.

---

## 3. Video Project State Machine

```
DRAFT ──► SCRIPT_GENERATING ──► SCRIPT_READY ──► SHOTS_GENERATING ──► SYNTHESIZING ──► COMPLETE
  │              │                    │                  │                   │
  │              ▼                    │                  ▼                   ▼
  │          SCRIPT_FAILED            │            SHOTS_FAILED        SYNTHESIS_FAILED
  │                                   │
  └──────────────────────────────► CANCELLED (from any non-terminal state)
```

| State | Description |
|---|---|
| `DRAFT` | Project created; brief not yet submitted |
| `SCRIPT_GENERATING` | LLM call in progress |
| `SCRIPT_READY` | Script generated; awaiting user approval |
| `SHOTS_GENERATING` | At least one shot is being generated |
| `SYNTHESIZING` | All shots complete; FFmpeg synthesis running |
| `COMPLETE` | Final video available for download |
| `SCRIPT_FAILED` | LLM call failed after retries |
| `SHOTS_FAILED` | One or more shots failed after retries |
| `SYNTHESIS_FAILED` | FFmpeg process failed |
| `CANCELLED` | User cancelled the project |

Terminal states: `COMPLETE`, `CANCELLED`, `SCRIPT_FAILED`, `SHOTS_FAILED`, `SYNTHESIS_FAILED`.

State transitions are recorded in `VideoProjectStateLog` with `(from_state, to_state, timestamp, triggered_by_user_id, notes)`.

---

## 4. Shot-Level State Machine

```
PENDING ──► QUEUED ──► GENERATING ──► COMPLETE
    │                       │
    │                       ▼
    │                  FAILED ──► PENDING (on manual retry)
    │
    └──► SKIPPED (if user deletes the shot before generation starts)
```

| State | Description |
|---|---|
| `PENDING` | Shot created; awaiting dispatch |
| `QUEUED` | Celery task dispatched; in Redis queue |
| `GENERATING` | Provider is processing the shot |
| `COMPLETE` | Clip downloaded and stored in S3 |
| `FAILED` | Provider returned an error; max retries exhausted |
| `SKIPPED` | Shot removed by user before generation |

A project enters `SYNTHESIZING` only when all non-skipped shots are `COMPLETE`.

---

## 5. FFmpeg Synthesis Pipeline

The synthesis worker runs a multi-step FFmpeg pipeline. All intermediate files are written to a temporary S3 prefix and cleaned up after synthesis completes.

**Step 1 — Normalize clips:** Each input clip is re-encoded to a common codec profile (H.264, AAC, 1080p, 30fps) to ensure compatibility before concatenation.

```bash
ffmpeg -i input.mp4 -vf scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080 \
  -r 30 -c:v libx264 -preset fast -c:a aac -ar 44100 normalized.mp4
```

**Step 2 — Concatenate:** A concat demuxer file lists all normalized clips in order. FFmpeg concatenates without re-encoding for speed.

```bash
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy concatenated.mp4
```

**Step 3 — Overlay captions:** On-screen text for each shot is rendered using `drawtext` filter with the project's font settings. Caption timing is derived from per-shot duration.

**Step 4 — Watermark:** The organization's logo is overlaid in the corner with `overlay` filter. Opacity is configurable (default 0.7).

**Step 5 — Audio mix:** If a background music track is specified, it is mixed with the clip audio using `amix`, with the music duck when voice-over is detected.

**Step 6 — Final output:** The assembled video is encoded to H.264/AAC MP4 at 8Mbps target bitrate, then uploaded to S3 under `{organization_id}/videos/{project_id}/final.mp4`.

---

## 6. Quality Check Checklist

Before a project can transition to `COMPLETE`, the synthesis worker verifies:

- [ ] Output file size > 10KB (sanity check against empty output)
- [ ] Output duration within 10% of target duration
- [ ] All declared shots are present in the output (verified by duration accounting)
- [ ] Audio track is present and not silent throughout (RMS check)
- [ ] Resolution is 1920×1080 (or specified target)
- [ ] Codec is H.264/AAC
- [ ] No FFmpeg stderr errors at level ERROR or above

If any check fails, the project transitions to `SYNTHESIS_FAILED` with a machine-readable reason code. The user can retry synthesis from the UI after reviewing the failure reason.

---

## 7. Provider Abstraction Design

The application never calls a video AI provider directly. All calls go through the `VideoProvider` protocol:

```python
class VideoProvider(Protocol):
    async def generate_shot(
        self,
        shot_id: str,
        description: str,
        duration_seconds: float,
        style_tokens: dict,
    ) -> ShotResult:
        ...

    async def get_shot_status(self, provider_job_id: str) -> ShotStatus:
        ...
```

Implementations:

| Class | Backend | Notes |
|---|---|---|
| `MockVideoProvider` | Local | Returns a placeholder colored MP4 clip. Used when `VIDEO_PROVIDER=mock`. Always synchronous. |
| `SeedanceVideoProvider` | Seedance API | Async; polls status endpoint until complete or failed. Requires `SEEDANCE_API_KEY`. |

Adding a new provider requires implementing the protocol and registering it in `app/video/providers/__init__.py`. No other code changes.

---

## 8. Copyright Compliance Requirements

**User-uploaded reference videos:**
- Uploading a copyrighted video for style extraction does not grant rights to reproduce its content.
- The system does not copy frames, audio, or any element of the reference video into the output.
- Style extraction outputs are descriptors (strings, numbers) — not copyrighted material.
- Users must confirm at upload time that they have the right to use the reference for internal analysis (TOS click-wrap).

**Generated content:**
- AI-generated video clips from Seedance or other providers are subject to each provider's terms of service regarding commercial use. Review provider TOS before enabling for commercial output.
- Background music tracks must be licensed (royalty-free or owned by the tenant). The system does not provide music; tenants upload their own assets.

**Brand assets (logos, fonts):**
- Only uploaded by the organization owner/admin, who certifies ownership at upload.

**Retaining records:**
- `VideoProject` records are soft-deleted only. The creation timestamp, uploader, and original brief are retained indefinitely for compliance purposes.

Legal counsel should review the TOS and user agreement before public launch.
