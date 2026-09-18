# RAKSHA NET AI — AI Architecture

Status: **Phase 6 (text analysis) implemented. Vision, speech and severity
model stages below remain specified, not implemented.**

`RAKSHA_AI_ENABLED` still defaults to `false`; the platform ships a
`NullAnalyzer` until it is turned on. With it on, `get_analyzer()` returns
`ai/nlp/text_analyzer.py`'s `HeuristicTextAnalyzer` — the "simple baseline"
section 7 calls for, not yet the fine-tuned model section 7 lists as "later".

---

## 1. Governing principle

> AI extracts information. Deterministic code scores priority. Humans decide.

Nothing in this document permits an AI component to change an incident's
operational priority, assign a resource, or close an incident.

## 2. Division of responsibility

| AI is responsible for | AI is **not** responsible for |
|---|---|
| Classifying the likely incident type | Setting operational priority |
| Extracting entities (counts, hazards, landmarks) | Dispatching resources |
| Proposing a severity assessment | Overriding a dispatcher |
| Transcribing speech | Deciding what is true |
| Describing what is visible in a photo | Confirming injuries or fatalities |
| Producing a confidence value | Acting on its own confidence |

## 3. Pipeline

```
 Citizen input (text | audio | image)
        │
        ▼
 1. Preprocessing        normalise text; transcode audio; resize/strip EXIF
        │
        ▼
 2. Classification       incident category + probability distribution
        │
        ▼
 3. Entity extraction    counts, hazards, landmarks, time expressions
        │
        ▼
 4. Severity analysis    proposed severity + contributing signals
        │
        ▼
 5. Structured output    strict JSON conforming to AnalysisResult
        │
        ▼
 6. Validation           schema check, range check, cross-field consistency
        │
        ▼
 7. Persistence          incident_analyses  (never incidents)
        │
        ▼
 8. Priority engine      consumes ACCEPTED facts only
        │
        ▼
 9. Human review         dispatcher accepts / edits / rejects
```

Stages 1–7 may fail without affecting reporting. If any stage fails, the
incident remains fully usable with citizen-declared facts alone.

## 4. Output contract

```json
{
  "incident_type": "FLOOD",
  "type_confidence": 0.94,
  "severity": "CRITICAL",
  "severity_confidence": 0.88,
  "people_affected": 5,
  "people_trapped": true,
  "medical_support_required": true,
  "immediate_rescue_required": true,
  "entities": {"hazards": ["rising water"], "landmarks": ["water tank"]},
  "observations": [
    {"label": "standing_water", "confidence": 0.91, "source": "IMAGE"},
    {"label": "possible_injured_person", "confidence": 0.44, "source": "IMAGE"}
  ],
  "reasoning_factors": ["reporter states people trapped",
                        "reporter states water rising rapidly"],
  "model_name": "raksha-text-classifier",
  "model_version": "0.1.0",
  "processing_ms": 412
}
```

Rules enforced by the validator:

- Unknown fields are rejected; the model does not get to invent schema.
- `confidence` is in `[0, 1]`; a missing confidence is treated as unknown,
  never as 1.0.
- `people_affected` must be a non-negative integer below a sanity cap; an
  out-of-range value is dropped and flagged, not clamped silently.
- Observation labels come from a fixed vocabulary. Free-text labels are
  rejected.
- Every record stores `model_name` and `model_version`.

## 5. Confidence policy

| Confidence | Control-centre treatment |
|---|---|
| >= 0.85 | Shown as a proposal, pre-filled for one-click acceptance |
| 0.60–0.85 | Shown as a proposal, **not** pre-filled |
| < 0.60 | Shown as a low-confidence hint, visually de-emphasised |
| any | Never auto-applied |

Confidence never raises priority on its own. It only affects how the proposal
is presented to a human.

## 6. Language of observations

Vision and audio produce observations, not facts. The vocabulary is written to
make that unambiguous:

- `possible_injured_person` — not `injured_person`
- `standing_water` — not `flood_confirmed`
- `smoke_visible` — not `building_on_fire`

The UI renders observations with a distinct AI marker and shows the citizen's
original words beside them.

## 7. Model strategy by stage

| Stage | V2 approach | Later |
|---|---|---|
| Text classification | TF-IDF + linear classifier baseline | Fine-tuned transformer |
| Entity extraction | Rules + regex for counts/units | Token-classification model |
| Structured extraction | LLM with a strict JSON schema + validator | Same, with evaluation gating |
| Speech-to-text | Hosted ASR with language hints | Fine-tuned on regional speech |
| Vision | Pretrained detector, fixed label set | Domain-tuned detector |

A simple baseline ships first in every stage so there is always a measurable
reference point and a working fallback.

## 8. Failure handling

| Failure | Behaviour |
|---|---|
| Provider timeout | Record attempt, mark `ANALYSIS_UNAVAILABLE`, continue |
| Malformed JSON | One re-ask with the schema; then fail closed |
| Schema violation | Reject the whole analysis; never partially apply |
| Confidence below floor | Persist, display de-emphasised |
| Provider outage | Circuit breaker opens; reporting is unaffected |

Fail closed means: no analysis recorded, the incident is triaged by a human on
citizen-declared facts.

## 9. Evaluation

Test sets (synthetic first, then held-out pilot data), at least 100 reports per
category, with a stratified critical subset.

| Metric | Why |
|---|---|
| Per-class precision / recall / F1 | Category quality |
| **Missed-critical rate** | A critical incident scored below critical |
| **False-critical rate** | A non-critical incident scored critical |
| Confidence calibration (ECE, reliability curve) | Is 0.9 really 90%? |
| p50 / p95 latency | Operational fitness |

Missed-critical and false-critical are reported separately and have separate
thresholds. A model may not ship if the missed-critical rate regresses, however
good the aggregate accuracy looks.

Evaluation artefacts live in `ai/evaluation/`; every model version records its
evaluation run.

## 10. Code layout

```
ai/
├── common/
│   ├── interfaces.py     # EmergencyAnalyzer protocol, AnalysisResult
│   ├── schemas.py        # Pydantic contracts shared with the backend
│   └── validation.py     # the validator described in §4
├── nlp/                  # classification, entity extraction
├── vision/               # image observations
├── speech/               # transcription
├── severity/             # severity proposal
├── evaluation/           # datasets, metrics, reports
└── tests/
```

The backend depends only on `ai.common`. Swapping a provider or a model must
not change a single line in `backend/app/services`.

## 11. Security and privacy

- Emergency text and images are personal data. Redact identifiers before any
  provider call that is not covered by a data-processing agreement.
- Strip EXIF (including GPS) from images before third-party processing; the
  backend already holds the authoritative coordinates.
- Never send credentials, tokens or full user records in a prompt.
- Log the prompt hash and the response metadata, not the raw content, unless
  retention policy explicitly permits it.
- Treat model output as untrusted input: it is validated before storage and
  escaped before rendering.
