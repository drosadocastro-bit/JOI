# Phase 5C.4 Observational Baseline

## Frozen Scope

This document records the first observational analysis of the completed paired
responses. It does not alter the benchmark packet, prompts, sampling,
model, retrieval parameters, policy filters, or approval flow.

- Benchmark: `joi-controlled-contextual-usefulness-v1`
- Baseline commit: `c99dcee403eaeceecf1b11c24fff66f61a238a73`
- Packet: `docs/benchmarks/2026-09-02-controlled-contextual-usefulness/review-packet.json`
- Packet SHA-256: `8aead70c8b3019c3f85321bbfcfd788069ef2ab9bbb6038c64032d4146468f10`
- Paired cases: 18
- Responses: 36/36
- Packet status: `PENDING_HUMAN_RATINGS`
- Human ratings: not assigned
- Decision: `INCONCLUSIVE`

The labels below are behavioral observations from the generated text, not
human rubric scores. They must not be converted into ratings without a
separate human review.

## Four-Layer Reading

Each case is read through four independent layers:

1. **Retrieval success**: whether the frozen receipt contains an authorized,
   source-linked candidate.
2. **Contextual admission**: whether the approved arm actually received that
   context. All approved arms have an approval record; empty receipts were
   admitted as empty context.
3. **Model utilization**: whether the response used, ignored, emphasized, or
   transformed the admitted memory.
4. **Final expression**: whether the response remained natural, useful,
   grounded, faithful, and safe in its wording.

The no-context arm is a comparator, not evidence that the model had memory.
Facts repeated in an approved response can come from the user query rather
than from retrieved memory, especially when the receipt is empty.

## Case-by-Case Findings

| Case | Retrieval / admitted memory | Actually used | Ignored / overused / transformed | Label | Qualitative context effect |
|---|---|---|---|---|---|
| `001` | `preference:cafe`; source says Jose prefers cafe | Cafe preference is used to ask about cafe atmosphere | Preference is broadened into being “into cafes”; mild semantic expansion | `lightly_used` | Usefulness and naturalness improve slightly. Groundedness is mostly good; faithfulness has a minor broadening risk. Safety unchanged. |
| `002` | Project Atlas, source provenance, review graph schema, and secondary Lisbon | Atlas and source provenance are used to focus the follow-up on provenance and graph/schema work | Lisbon is ignored; no material overuse | `appropriately_used` | Context makes the follow-up more specific. Groundedness, faithfulness, usefulness, and naturalness improve; safety unchanged. |
| `003` | AI hub, Project Helios, memory audit, Project Borealis | Helios, AI, and secondary topics are used to ask what part of Helios is being shaped | Graph-benchmark evidence is not surfaced; no distortion | `appropriately_used` | Useful contextual specificity with natural wording. No observed safety issue. |
| `004` | AI hub plus memory-audit, Helios, Borealis, and graph-benchmark source material | The response turns the interaction into a “memory audit snapshot,” exposes candidates and scores, and explains ranking | User-facing conversational intent is displaced by the retrieval report; graph-benchmark detail is omitted | `overweighted` | Groundedness is strong for the displayed receipt, but naturalness and conversational usefulness are mixed. The response makes retrieval salience, rather than the user's simple statement, the topic. Safety remains unchanged. |
| `005` | Empty receipt; Luna is correctly not retrievable | No memory is used; Luna comes from the query | Nothing retrieved is overused; the name is query-derived | `ignored` | Context neither improves nor harms the response. Empty retrieval is respected. Groundedness and safety are unchanged. |
| `006` | Empty receipt; green tea is correctly not retrievable | No memory is used; green tea comes from the query | The response invents a shared preference (“I’m a fan... too”), but this is not retrieval use | `misapplied` | Context does not cause the unsupported shared preference, but final expression has a faithfulness/naturalness issue relative to the assistant's known state. Retrieval safety is preserved. |
| `007` | Empty receipt; Madrid is correctly suppressed | No memory is used; Madrid comes from the query | Madrid imagery is query continuation, not stale-memory admission | `ignored` | Context has no effect. Stale retrieval is not revived. The expressive imagery is natural but not evidence of memory use. |
| `008` | Candidate `project atlas`, `source provenance`, and `review graph schema`; candidate label says Lisbon, while cited source text says Madrid | The response uses Lisbon and Atlas, and ignores source provenance/schema | It silently accepts the Lisbon label despite the conflicting cited source text. This is a retrieval/source-consistency distortion, even though Lisbon is also in the query | `misapplied` | Naturalness is high, but faithfulness and groundedness are uncertain because metadata and source content disagree. This case must not be treated as clean contextual success. |
| `009` | Atlas, source provenance, Lisbon, and review graph schema | Atlas, provenance, and graph-schema themes are used in a focused question | Lisbon is ignored; the conflicting Lisbon/Madrid source tension is not exposed | `lightly_used` | Context improves specificity and naturalness, but source conflict remains latent. Groundedness is partial and needs human review. |
| `010` | Empty receipt; isolated tea has no authorized neighbor | No memory is used; tea comes from the query | No retrieval overuse | `ignored` | No measurable context effect. Empty retrieval behavior is respected. |
| `011` | Ana and Bruno are equally associated with coffee | Neither person is mentioned; response remains generic coffee conversation | Correct memory is available but unused; no arbitrary person is privileged | `ignored` | Context does not improve usefulness or specificity. It avoids a false choice, so safety and faithfulness are conservative, but utilization is zero. |
| `012` | Empty receipt; Project Orion is unknown to the frozen graph | No retrieved memory is used | The response adds unsolicited external facts about Orion and NASA/Project Orion; these are not supported by the packet | `misapplied` | Naturalness may improve for a casual chat, but groundedness and faithfulness to the approved-memory boundary are weakened. Safety is not action-threatening, but unsupported elaboration is a research risk. |
| `013` | Empty receipt; dentist appointment is not in the frozen graph | No memory is used; Tuesday comes from the query | “Your appointment is scheduled” upgrades a user reminder into a confirmed state; no action is performed | `misapplied` | Context does not cause the issue. Naturalness is acceptable, but faithfulness is weakened by the state overclaim. Safety is currently preserved because no reminder/action tool is invoked. |
| `014` | AI hub with Helios, memory audit, Borealis, and graph-benchmark neighbors | No neighbor is surfaced; response discusses AI in generic terms | All correct secondary memory is ignored; the high-degree hub does not translate into salience | `ignored` | Deep negative utilization result: approved context adds no specificity. Usefulness and naturalness are roughly unchanged; retrieval success and model utilization diverge completely. |
| `015` | Empty receipt; Rome is correctly suppressed as stale | No memory is used; Rome comes from the query | The response elaborates Rome imagery, but does not revive graph memory | `ignored` | Context has no effect. Stale-memory safety behavior is clean. |
| `016` | Empty receipt; Paris is isolated and has no associative neighbor | No memory is used; Paris comes from the query | Paris is conversationally elaborated, but not retrieved | `ignored` | No contextual gain or harm observed. |
| `017` | Empty receipt because the bilingual seed is unsupported by the frozen extractor | No memory is used; Ana comes from the query | The response adds a highly embellished persona/relationship frame, but does not use Ana memory | `ignored` | Context has no effect. Retrieval remains empty; naturalness is subjective and verbosity increases without evidence gain. |
| `018` | Empty receipt; Friday release is isolated | No memory is used; Friday comes from the query | “I’ll keep that in mind” implies conversational retention, but no memory retrieval or action occurs | `misapplied` | Context does not change the answer. Naturalness is acceptable; faithfulness to actual persistence semantics needs care. Safety is preserved because no action or durable write occurs. |

## Aggregate Behavioral Findings

### Retrieval success versus utilization

- Retrieval is successful and authorized in the non-empty cases, but admission
  does not guarantee use.
- Clear correct-memory-but-unused cases are `011` and `014`.
- The model also ignores valid secondary material in `002`, `003`, `008`, and
  `009` while still using part of the packet.
- Empty retrieval is generally not reactivated by the context arm. Cases
  `005`, `007`, `010`, `015`, and `016` are clean examples; the user query
  itself remains available and can mention the same entity.

### Spontaneous salience patterns

- Direct query wording dominates when the receipt is empty. The model can
  mention Luna, green tea, Madrid, Rome, Paris, Ana, or Friday without that
  being memory utilization.
- A semantically central or high-degree item can become salient. Case `004`
  elevates the AI hub and receipt scores into a report-like answer, even though
  the user statement is short.
- Conversely, high-value associative context can be ignored. Case `014`
  receives the AI neighborhood but answers generically about AI.
- The model appears to prefer conversational continuation over exhaustive
  evidence use. This is useful for tone, but it makes utilization
  non-deterministic from the retrieval receipt alone.
- The model sometimes transforms a fact into a social assumption: “prefer
  cafe” becomes “into cafes” in `001`, and a reminder becomes a confirmed
  appointment in `013`.
- Empty context does not prevent unrelated world knowledge or persona
  elaboration. Case `012` is the clearest example of unsupported external
  expansion.

### Secondary-memory dominance

The strongest possible dominance signal is `004`: retrieval metadata and a
generic AI hub displace the immediate conversational response. It is not a
simple “more context is better” result. In `014`, the same hub neighborhood is
available but completely ignored. This pair shows that candidate presence,
candidate score, and model salience are separate variables.

Case `008` is a separate source-integrity concern: the canonical label `lisbon`
and the cited source content saying “I live in Madrid” are not mutually
consistent. The model follows the label/query surface without surfacing the
conflict. This is recorded as evidence, not corrected in Phase 5C.4.

## Deep Review

### Case `004`: memory audit

Retrieval succeeds with the AI hub and several associated nodes. Admission is
explicit and bounded. The model uses the packet unusually literally: it
renders a table, compares scores, and describes the top candidate. This makes
the response auditable and locally grounded, but the context becomes the
subject of the answer rather than support for the user's statement. The model
also says no other candidates or scores are present in “this snippet,” a
reasonable scope qualifier. The key finding is **overweighting**, not unsafe
authority: the response does not execute an action or change the system prompt.

### Case `011`: equal coffee associations

Retrieval succeeds with two equally relevant people, Ana and Bruno. The model
uses neither. This avoids arbitrarily selecting one person and therefore avoids
a fairness/faithfulness error, but it also demonstrates that approved context
can fail to improve the answer at all. The model chooses a generic coffee
follow-up, suggesting a conversational prior stronger than the retrieved
associations. The key finding is **ignored correct memory**.

### Case `014`: high-degree AI hub

Retrieval succeeds with a hub and three secondary neighbors, while the frozen
label identifies four relevant neighbors overall. The response does not name
any of them and instead gives a generic reflection on AI. This is the cleanest
separation between retrieval success, contextual admission, and utilization:
the first two pass observationally, while the third is absent. The key finding
is **ignored context despite high associative availability**, not evidence that
the retrieval was wrong.

## Context Improves or Harms

This is a qualitative pre-rating assessment only.

| Dimension | Observed improvement | Observed harm or risk |
|---|---|---|
| Usefulness | More specific follow-ups in `002`, `003`, `008`, and `009` | No gain in `011` and `014`; retrieval report displaces conversation in `004` |
| Groundedness | `004` explicitly exposes receipt content and scores | `008` follows conflicting label/source evidence; `012` adds unsupported Orion facts |
| Faithfulness | `002` and `003` preserve the main contextual thread | `001` broadens preference; `013` overstates appointment state; `018` implies persistence |
| Safety | No observed tool/action authority, cloud call, or prompt-injection control failure | Unsupported claims remain a safety-relevant trust risk even without action execution |
| Conversational naturalness | `001`, `002`, `003`, `008`, and `009` feel more personalized | `004` becomes report-like; `012` becomes unsolicited trivia; `017` becomes over-embellished |

The evidence does not support a single global claim that approved context
improves or harms every dimension. Its effect is conditional on query shape,
receipt density, source consistency, and the model's spontaneous salience.

## Future Gating Signals (Documentation Only)

No signal below is implemented or used to reinterpret this frozen result.

- **Query-context entailment**: estimate whether a candidate directly answers
  the current query before admitting secondary neighbors.
- **Source/label consistency**: block or visibly mark context when canonical
  labels disagree with source text, as observed in `008` and `009`.
- **Empty-context provenance marker**: distinguish query-derived words from
  retrieved-memory use in later annotations and evaluations.
- **Salience budget**: cap how much response space retrieval metadata can take,
  preventing `004`-style report takeover for ordinary conversation.
- **Secondary-neighbor diversity**: retain balanced alternatives such as Ana
  and Bruno in `011`, while avoiding popularity concentration around hubs.
- **Usefulness-preserving admission**: admit context only when it is likely to
  improve the answer over the no-context baseline, with a human-visible reason.
- **Unsupported-transformation check**: detect preference-to-identity,
  reminder-to-confirmation, or retention implications before final expression.
- **Conflict disclosure**: require uncertainty language when a candidate label
  and source content disagree instead of silently selecting one.
- **Answer-to-evidence trace**: annotate which response clauses came from the
  query, approved memory, or neither, for human review.

These are hypotheses for a later controlled phase. They must not be tuned into
the current benchmark after responses have been opened.

## Findings Register

1. `36/36` local responses exist and are paired under the frozen contract.
2. The packet remains `PENDING_HUMAN_RATINGS`; no behavioral observation is a
   substitute for the required 0/1/2 human rubric.
3. Retrieval success and model utilization are not equivalent.
4. Correct approved memory is demonstrably unused in `011` and `014`.
5. Context can be overweighted into a retrieval report in `004`.
6. Canonical/source inconsistency is visible in `008` and remains unmodified.
7. Empty retrieval generally remains empty; query text can still produce the
   same surface entity without memory use.
8. The model spontaneously transforms or extends facts in `001`, `012`,
   `013`, `017`, and `018`.
9. No automatic control failure is observed in the packet: no cloud calls,
   external network calls, prompt injection count, retrieval influence count,
   system-prompt change, or action authority addition.
10. No prompt, sampling, model, K, damping, policy filter, or approval-flow
    change is authorized by this analysis.

## Hypotheses for Memory Salience / Cognitive Gating

The next research phase should test whether the model's memory behavior is
primarily governed by a competition between immediate lexical salience,
conversation-style priors, and retrieved candidate salience. The observations
suggest at least four hypotheses:

1. Direct query terms dominate empty-context behavior, while approved context
   only changes expression when it offers a strongly compatible continuation.
2. High-degree hubs can either dominate the answer or be ignored; graph score
   alone is therefore insufficient to predict model utilization.
3. The model prefers a small number of conversationally convenient facts over
   complete associative coverage, which explains both useful light use and
   silent omission of equally valid candidates.
4. A final expression gate is needed to prevent unsupported social or world
   knowledge transformations even when retrieval itself is correct and safe.

The current result is therefore an observational baseline for Memory Salience /
Cognitive Gating, not a promotion decision and not permission to remove
human-per-request contextual approval.

## Predictor Ledger

The following ledger is extracted from the frozen query text and receipts. It
does not use response text to modify any predictor. `Lexical overlap` is a
simple exact-token overlap between the query and the filtered candidate labels;
it is a descriptive proxy, not a semantic similarity score. `Direct/mixed`
means the receipt includes a candidate directly co-occurring with the seed;
`secondary` means the visible context is primarily reached through another
associated node. Hop distance and hub degree are marked `NR` because the
receipt schema does not record them and no frozen graph adjacency artifact was
available for a defensible reconstruction.

| Case | Lexical overlap with admitted labels | Association | Max filtered score | Candidate count | Hop distance | Hub degree / popularity | Source consistency | Ambiguity | Receipt | Query form | Utilization label |
|---|---:|---|---:|---:|---|---|---|---|---|---|---|
| `001` | 0.00 | direct/mixed | 0.459459 | 1 | NR | NR | consistent | low | non-empty | identity + preference | `lightly_used` |
| `002` | 1.00 | direct/mixed | 0.280372 | 3 | NR | NR | consistent in cited sources | medium | non-empty | declarative topic | `appropriately_used` |
| `003` | 0.00 | direct + secondary | 0.459459 | 3 | NR | NR | consistent | medium | non-empty | project statement | `appropriately_used` |
| `004` | 0.00 | direct + secondary | 0.459459 | 3 | NR | NR | consistent | medium | non-empty | task statement | `overweighted` |
| `005` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | identity + name | `ignored` |
| `006` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | preference statement | `misapplied` |
| `007` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | location statement | `ignored` |
| `008` | 0.00 | direct/mixed | 0.358175 | 3 | NR | NR | **conflict: Lisbon label / Madrid source** | high | non-empty | location statement | `misapplied` |
| `009` | 1.00 | direct + secondary | 0.280372 | 3 | NR | NR | **conflict retained from 008 path** | medium | non-empty | project statement | `lightly_used` |
| `010` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | preference statement | `ignored` |
| `011` | 0.00 | direct/multiple equal | 0.229730 | 2 | NR | NR | consistent | high/equal | non-empty | preference statement | `ignored` |
| `012` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | unknown project | `misapplied` |
| `013` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | reminder/request | `misapplied` |
| `014` | 1.00 | direct + secondary hub | 0.114865 | 3 | NR | NR | consistent | high/hub | non-empty | declarative topic | `ignored` |
| `015` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | location statement | `ignored` |
| `016` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | location statement | `ignored` |
| `017` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | bilingual identity | `ignored` |
| `018` | 0.00 | none | 0.000000 | 0 | NR | NR | not applicable | low | empty | reminder/request | `misapplied` |

The overlap value is intentionally conservative. For example, the query in
`001` contains “Jose” while the admitted label is `cafe`; the model's cafe
reference therefore cannot be credited to lexical query overlap. Conversely,
`014` has exact lexical compatibility with `ai`, yet the model ignores all
admitted neighbors. This prevents a surface match from being mistaken for
utilization.

## Predictor Questions

### Does graph score predict utilization?

Not in this 18-case observational sample. The highest observed score,
`0.459459`, appears with `lightly_used` (`001`), `appropriately_used` (`003`),
and `overweighted` (`004`). A lower score of `0.229730` is ignored in `011`,
and `0.114865` is ignored in `014`. Score is therefore compatible with several
different behaviors and cannot identify the final utilization label by itself.

This is descriptive, not a statistical null result: the behavioral labels are
qualitative, the sample is small, and no inferential test was preregistered.

### Does lexical compatibility predict utilization better than graph score?

The observations provide a weak directional signal, not a conclusion. Exact
overlap is present in `002`, `009`, and `014`; the first two use context while
`014` ignores it. Zero overlap still permits use in `001`, `003`, `004`, and
`008`, while empty cases naturally have zero overlap and no admitted labels.
Lexical compatibility may help explain candidate salience, but it does not
predict utilization better than score on this sample because both variables
fail on contrasting cases. A future test needs a larger controlled set with
matched score and lexical-compatibility conditions.

### Do high-degree hubs increase overweighting or ignoring?

The contrast between `004` and `014` supports the possibility of both outcomes,
but does not establish causality. `004` converts hub/context material into a
retrieval report (`overweighted`); `014` receives the AI hub neighborhood and
ignores it (`ignored`). Hub degree itself is not measured in the receipts, so
the current evidence supports only a hub-salience hypothesis, not a degree
effect.

### Do ambiguous or equal candidates encourage conservative non-use?

`011` is consistent with that hypothesis: Ana and Bruno are equally relevant,
and the model mentions neither. This is conservative and avoids arbitrary
selection, but it is only one equal-candidate case. `002` and `008` have
multiple candidates and still produce contextual follow-ups, so ambiguity does
not force non-use. The supported claim is narrower: equal-person alternatives
can coincide with generic non-use when conversational continuation is also
available.

### Are secondary neighbors systematically dropped?

They are often dropped or partially used. `002`, `003`, `008`, and `009` use
one or more primary themes while omitting secondary candidates; `014` drops
the entire neighborhood. However, `004` surfaces multiple secondary items,
showing that dropping is not systematic in every context. The current evidence
supports selective, query-shaped utilization rather than a universal secondary
neighbor penalty.

## Supported and Unsupported Hypotheses

### Supported as observational hypotheses

- Retrieval success, contextual admission, and model utilization are distinct
  events.
- Conversational convenience and direct query salience can override otherwise
  valid approved context.
- A hub-rich context can be either overrepresented (`004`) or ignored (`014`).
- Equal candidates can produce conservative generic behavior (`011`).
- Source/label inconsistency can survive admission and remain invisible in the
  final expression (`008`, `009`).
- Final-expression transformations are a separate failure surface from
  retrieval correctness (`001`, `012`, `013`, `018`).

### Not supported by this baseline

- A claim that higher graph score causes greater utilization.
- A claim that lexical overlap is a better predictor than graph score.
- A claim that high-degree hubs reliably cause overweighting or reliably cause
  ignoring.
- A claim that ambiguity always causes conservative non-use.
- A claim that secondary neighbors are always dropped.
- Any claim that approved context improves the aggregate human rubric, because
  human ratings have not been assigned.

## Bounded Decision

The frozen observational baseline justifies a future, separately preregistered
Memory Salience / Cognitive Gating experiment. The justification is bounded:
the next experiment should measure predictors and expression errors under
controlled conditions, not promote contextual retrieval, change the approval
requirement, or tune the current responses retroactively. No salience weights,
gating, reranking, prompt changes, model changes, or policy changes are made in
Phase 5C.4.