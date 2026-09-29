# Phase L8 — Voice Evidence Pipeline Verification & Audit Report
**Cyclone Twin — Critical Access Restoration Engine**

---

## 1. Executive Summary

Phase L8 extends the Multimodal Field Intelligence framework to support field operator **voice recordings** (.wav, .mp3, .ogg, .webm, max 25MB). 

Like the image/photograph evidence pipeline (Phase H), Phase L8 enforces a strict two-step separation:
1. **Transcription & Extraction (Step 1)**: Audio is transcribed and candidate evidence is extracted into an intermediate domain contract (`MultimodalEvidenceExtraction`). This phase is **100% read-only** (guarantees 0 state mutation on `NetworkEngine`, `DisasterState`, or operational priorities).
2. **Phase E Validation & Reconciliation (Step 2)**: Candidate evidence must be reviewed by operators (with optional coordinate resolution) and submitted through Phase E input validation and deterministic reconciliation. State mutation occurs **only** when Phase E reconciliation criteria are satisfied.

---

## 2. Architecture & Domain Models

### 2.1 Core Entities

```
VOICE ARTIFACT (.wav/.mp3/.ogg)
       │
       ▼ (validate upload: MIME, size ≤ 25MB, duration)
VoiceArtifactMetadata (provenance, timestamp, source)
       │
       ▼ (Gemini 2.5 Flash / Deterministic Fallback)
VoiceTranscriptionResult (transcript, transcription_confidence, language)
       │
       ▼ (structured evidence mapping)
MultimodalEvidenceExtraction (observation_type, location, depth, extraction_confidence)
       │
       ▼ (Phase E Input Validation & Deterministic Reconciliation)
InfrastructureObservation → NetworkEngine state update
```

### 2.2 Distinct Metrics Rule

To prevent conflating speech recognition accuracy with observation reliability:
- **`transcription_confidence`**: Measures acoustic clarity and word accuracy (e.g. 0.85).
- **`extraction_confidence`**: Measures how strongly the transcribed text maps to a specific road blockage or flood depth (e.g. 0.65).
- Both metrics are maintained as separate, unmerged fields inside `VoiceTranscriptionResult` and `MultimodalEvidenceExtraction.uncertainty`.

---

## 3. Safety & Defense Mechanisms

### 3.1 Spoken Prompt Injection Defense
- Audio transcripts are treated as **untrusted witness testimony**.
- The `_sanitize_transcript()` utility strips control characters (`{}[]<>`) and instruction syntax.
- System prompts explicitly instruct the transcription provider to ignore spoken command phrases (e.g., "ignore previous instructions") and treat spoken input purely as data.

### 3.2 File Validation & Security
- **MIME Enforcement**: Rejects unsupported MIME types (`audio/wav`, `audio/mpeg`, `audio/ogg`, `audio/webm`, `audio/mp4`, `audio/aac`).
- **File Size Limits**: Enforces minimum payload (64 bytes) and maximum payload (25 MB).
- **Path Traversal Protection**: Rejects filenames containing `..`, `/`, or `\`.

---

## 4. API Contract

### `POST /observations/voice/transcribe`
- **Request**: Multipart form with `audio` (UploadFile), `source_type`, `lat`, `lon`, `duration_sec`, `language_hint`.
- **Response**: `{ "artifact": VoiceArtifactMetadata, "transcription": VoiceTranscriptionResult, "extraction": MultimodalEvidenceExtraction }`
- **State Guarantee**: Read-only (0 state mutation).

### `POST /observations/voice/ingest`
- **Request**: `{ "extraction_id": str, "location_override": [lat, lon] }`
- **Response**: Ingestion result via Phase E pipeline (`status`, `observation`, `reconciliation`, `state_before`, `state_after`, `provenance_lineage`).

---

## 5. Verification & Test Suite Summary

- **Backend Test Suite**: 291/291 tests passed (13 new Phase L8 voice pipeline tests).
- **Frontend Build**: Passed (0 errors, built in 263ms).
- **Frontend Lint**: 0 errors.
- **Invariants Verified**:
  - `Forecast != Observation != State`
  - `Vulnerability != Restoration Priority`
  - `Voice Transcription != State Mutation`
  - `Phase E` remains sole state mutator.
