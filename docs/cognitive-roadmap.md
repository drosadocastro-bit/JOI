# Cognitive And Relational Roadmap

## Scope

This roadmap extends JOI from memory toward relational continuity, contextual
adaptation, bounded initiative, and controlled learning. It does not claim
consciousness, subjective feelings, hidden emotional access, or autonomous
self-directed goals.

Development order:

> Memory first. Continuity next. Agency last.

Later layers are not unlocked merely because earlier code exists. Every layer
requires its own evidence, acceptance gate, feature flag, inspection path, and
graceful failure behavior.

## Gate 0: Memory Trust Foundations

Relational inference must not begin until ordinary memory can be evaluated and
corrected safely.

Required foundations:

- explicit memory read and injection policy
- inspection with raw source-turn provenance
- correction through supersession rather than historical erasure
- forget/delete policy that distinguishes logical suppression from physical
  deletion
- contradiction representation and current-statement precedence
- shadow retrieval with relevance, false-recall, and provenance measurements
- confidence calibration and empty-context fallback

### Gate

- user corrections outrank stored and inferred memory
- every retrieved claim resolves to inspectable source evidence
- low-confidence or failed retrieval reduces to normal conversation
- stale memory cannot override the current user statement
- retrieval quality is measured before relational memories consume it

Compact Memory's prerequisite model-backed shadow evaluation is specified in
[compact-memory-closure-gate.md](compact-memory-closure-gate.md). That gate
must pass before graph, vector, relational, or live memory retrieval work can
use Compact Memory claims.

## Phase A: Relational Continuity

### A1: Relational Candidate Schema

Capture observable interaction patterns without converting them into claims
about hidden emotional states.

Candidate fields should include:

- stable candidate ID and schema version
- contextual key, such as `technical_workflow.response_style`
- proposed value
- explicit or inferred authority
- supporting and contradicting source turn IDs
- first and last observed timestamps
- confidence, reinforcement count, and expiry or review time
- status: candidate, active, superseded, rejected, or expired

Examples of eligible evidence include explicit response preferences, recurring
language choices, repeated corrections, topic-dependent tone, and accepted
workflow patterns. Prefer contextual claims over global labels.

An explicit preference may qualify from one direct statement. An inferred
pattern requires repeated independent observations. Negative evidence and user
corrections lower confidence.

### Gate

- every pattern is provenance-linked and inspectable
- inferred patterns are labeled inferred
- no hidden-emotion claim can pass schema validation
- correction creates a superseding record
- single observations cannot silently become durable inferred policy

### A2: Relational Shadow Learning

Generate relational candidates without changing responses. Compare proposed
patterns against later corrections, repeated evidence, and actual interaction
outcomes.

Track false preference inference, stale patterns, contradiction rate, evidence
count, candidate acceptance, and user correction frequency.

### Gate

- candidate precision meets an agreed threshold
- candidate and evidence inspection is available
- disabled mode produces no candidates or behavioral changes
- no silent adaptation occurs

### A3: Shared Continuity Retrieval

Retrieve relevant prior interactions naturally and sparingly. A callback must
pass relevance and confidence thresholds and retain its internal source memory
ID. Empty, weak, stale, or failed retrieval must behave like memory-disabled
conversation.

### Gate

- callbacks are contextually relevant in evaluation
- old interactions are not forced into unrelated responses
- current statements always outrank recalled context
- retrieval failure does not affect text or voice operation

### A4: Interaction Context State

Maintain lightweight, session-scoped operational context such as conversation
mode, language style, response depth, current theme, and requested tone.

This state is derived and explainable, not authoritative. It must not include a
relationship score, affection meter, hidden emotion classifier, or claim about
the user's internal state.

### Gate

- state changes reconstruct from recent evidence
- reset and degradation are deterministic
- developer inspection explains each active field
- no hidden scoring system exists

## Phase B: Contextual Adaptation

### B1: Adaptive Response Policy

Permit bounded changes to verbosity, playfulness, directness, technical depth,
code-switching, question frequency, and pacing while keeping JOI's identity,
truthfulness, privacy, and safety contracts fixed.

### B2: Relational Pattern Activation

Activate only proven low-risk interaction preferences. Explicit instructions
override inference. Weak inferred preferences expire or return to candidate
state without deleting their evidence.

### Gate

- user override is immediate
- provider or model replacement does not redefine identity
- every adaptation names its evidence and active scope
- rollback restores the prior policy version
- no permanent adaptation arises from a single inferred event

## Phase C: Interaction Regulation State

Use operational variables rather than emotion claims. Candidate variables may
include uncertainty, confidence, novelty, urgency, social warmth,
interaction load, topic sensitivity, and engagement priority.

Each variable requires a computational definition, bounded range, input
signals, update rule, decay/reset rule, and observable behavioral consequence.
Initial updates should be deterministic or reconstructable without a black-box
emotion classifier.

Expression modes such as normal, playful, quiet, supportive, focused, or
cinematic may modulate delivery but cannot create separate identities or
override factual, safety, privacy, and authorization policy.

### Gate

- every variable maps to observable behavior
- transitions are inspectable and reconstructable
- no variable is presented as proof of subjective feeling
- user can change or disable expression mode
- interaction regulation cannot manipulate attachment

## Phase D: Bounded Initiative

### D1: Initiative Candidates

Generate sparse suggestions from current context and approved memory, then pass
them through relevance, frequency, privacy, and policy checks. Suggestions may
revisit unfinished ideas or propose a next experiment; they never execute an
action by themselves.

### D2: Goal Candidates

Represent temporary goals with an explicit source, scope, confidence, expiry,
and required authority. Allowed sources are user requests, current context,
approved policy, and bounded maintenance tasks.

Prohibit secret goals, unrestricted self-preservation goals, self-granted
permissions, and unapproved persistent autonomous objectives.

### Gate

- initiative frequency and irrelevance are measurable
- initiative can be globally disabled
- every goal has provenance, scope, and expiry
- no goal can grant authority or bypass approval

## Phase E: Agentic Behavior

All future actions use this boundary:

```text
observation
  -> goal candidate
  -> action candidate
  -> policy and authorization
  -> human approval when required
  -> bounded tool execution
  -> validated result and audit receipt
```

There is no direct LLM-to-arbitrary-tool path. MCP begins with read-only
resources, deny-by-default capability policy, scoped credentials outside the
reasoning layer, validated inputs and outputs, and a global disable control.

### Gate

- threat model and adversarial authorization tests pass
- consequential actions require explicit human approval
- compromised tools cannot alter identity, memory policy, or permissions
- every execution produces an auditable receipt

## Phase F: Controlled Learning

Learning initially changes no model weights, source code, permissions, or
personality contract. Experience produces provenance-linked candidate policy
changes that are evaluated in shadow mode.

Track accepted and rejected candidates, false preference inference,
over-adaptation, stale behavior, corrections, and outcome quality. Only proven
low-risk conversational adaptations may later be approved, versioned, expired,
and rolled back.

### Gate

- candidate changes preserve evidence and rationale
- shadow precision meets an agreed threshold
- prior policy versions remain recoverable
- user correction outranks learned behavior
- no silent behavior drift occurs

## Phase G: Relational Consolidation

Extend future read-only dreaming only after relational retrieval and shadow
learning are proven. Consolidation may find repeated patterns, stale
assumptions, contradictions, aliases, and candidate salience changes.

Dream output remains hypothetical. It may not invent emotional history, create
attachment claims, rewrite raw conversation, promote unsupported inference to
fact, or grant goals and permissions.

## Cognitive Invariants

1. Memory is evidence, not truth.
2. Inference is not observation.
3. Association is not fact.
4. Interaction regulation is not subjective feeling.
5. Adaptation is not identity replacement.
6. Initiative is not authority.
7. Goals require provenance, scope, and expiry.
8. Learning produces candidates before policy changes.
9. Current user statements and corrections outrank inference.
10. JOI cannot self-grant permissions.
11. Personality, privacy, and safety policy cannot change silently.
12. Private context cannot be uploaded silently.
13. Every durable adaptation is inspectable and reversible.
14. Every adaptive subsystem degrades without breaking conversation.
15. Provider and model changes cannot redefine JOI's identity.

## Evaluation Questions

- Does relational memory improve continuity without increasing false recall?
- What evidence threshold controls each inferred preference type?
- How often are contextual preferences incorrectly generalized?
- How quickly should weak inferred preferences expire?
- Does adaptation remain stable across local and future cloud models?
- Can initiative remain useful, sparse, and non-intrusive?
- Does interaction regulation improve delivery without emotion claims?
- Does consolidation improve candidate quality or amplify errors?
- Which adaptations can remain entirely local and inspectable?

## Approved Implementation Order

```text
memory correction and inspection
  -> shadow retrieval evaluation
  -> relational candidate schema
  -> relational shadow learning
  -> shared continuity retrieval
  -> interaction context
  -> contextual adaptation
  -> interaction regulation state
  -> bounded initiative
  -> authorized action pipeline
  -> shadow controlled learning
  -> approved adaptation
  -> relational consolidation
```

> Replay broadly. Infer cautiously. Commit conservatively.
