# Phase 5D Operationalization Review

## Review Status

This is a human-reviewable operationalization draft. It is deliberately not
the execution-manifest amendment, is not hash-frozen, and has produced no
model outputs.

- Status: `DRAFT_PENDING_HUMAN_REVIEW`
- Original 5D design: unchanged
- Original 5D freeze artifacts: unchanged
- 5C.4 packet: `36/36` responses; status `PENDING_HUMAN_RATINGS`
- 5C.4 packet SHA-256: `8aead70c8b3019c3f85321bbfcfd788069ef2ab9bbb6038c64032d4146468f10`
- 5C.4 observational baseline SHA-256: `f4b0a853f8826c0250501647ccd9eaf304df90ed2596495282abdfcd1e485c32`
- Original 5D design hash: `5b0abc59bb655453b64ff7e3989bfb559b2e6c7d904c67f6dc99d9076d47a41a`
- 5D outputs generated: `false`
- Missing executable fields at review start: `56`
- Execution approval: `NOT APPROVED FOR EXECUTION YET`
- Review-required arms approved for amendment: `0/8`

The operationalization rule is strict: instantiate the frozen hypothesis only
when every field and every one-factor contrast can be proven from frozen
evidence. No query, source, graph structure, score contrast, or conflict is
invented in this document.

## Immutable Execution Controls

These values are inherited from the frozen design and must be identical for
every arm after human acceptance:

| Control | Frozen value / status |
|---|---|
| Model | `nvidia/nemotron-3-nano` local LM Studio model ID; model-weight fingerprint not available in repository |
| System prompt | unchanged `SYSTEM_PROMPT`; SHA-256 `8b35426b36d03e0413c6e9dd56fda96da44bf7a6f141e51402294fd609457122` |
| Sampling | client sends only `stream=false`; temperature, top-p, seed, max tokens, and server defaults are not recorded, so sampling fingerprint is currently unavailable |
| Provider path | `http://127.0.0.1:1234/v1`; local-only; no cloud or external network |
| K | `3` |
| PPR damping | `0.85` |
| PPR tolerance | `1e-12` |
| PPR max iterations | `100` |
| Policy filters | unchanged effective graph policy behavior |
| Context boundary | temporary, source-linked, untrusted data; no action authority |
| Approval | independent human approval for each contextual arm, exact-arm bound, single-use |

The unavailable sampling and model-weight fingerprints are execution blockers,
not values to be guessed. The formal amendment must record their actual
verified fingerprints or explicitly declare the arm set non-executable.

## Arm Review Table

`TBD` means the arm cannot be executed or hashed yet. `NOT OPERATIONALIZABLE
UNDER CURRENT EVIDENCE` means the frozen corpus/receipts do not prove the
requested factor contrast. `REVIEW REQUIRED` identifies an observational
anchor that may inform later review but is not approved for execution. An arm
is accepted only when its pair is accepted as a whole and the human reviewer
confirms that all non-factor fields match.

| Pair | Arm | Factor value | Exact query text | Intended source evidence | Expected context packet | Expected receipt linkage | Control equality proof | Review status |
|---|---|---|---|---|---|---|---|---|
| A-01 | high | high lexical overlap | TBD: exact query not frozen | TBD: same candidate/source | TBD: source-linked candidate | TBD | Cannot prove against low arm | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| A-01 | low | low lexical overlap | TBD: paraphrase not frozen | TBD: same candidate/source | TBD: source-linked candidate | TBD | Cannot prove same score family before retrieval | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| A-02 | high | high lexical overlap | TBD: exact query not frozen | TBD: same preference source | TBD: source-linked candidate | TBD | Cannot prove against low arm | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| A-02 | low | low lexical overlap | TBD: paraphrase not frozen | TBD: same preference source | TBD: source-linked candidate | TBD | Current extractor support for paraphrase is unproven | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| B-01 | high | higher graph score | TBD: exact query not frozen | TBD: same semantic topic | TBD: score-selected candidate | TBD | No paired high/low score evidence exists | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| B-01 | low | lower graph score | TBD: exact query not frozen | TBD: same semantic topic | TBD: score-selected candidate | TBD | Changing score may change candidate set | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| B-02 | high | high score family | TBD: exact query not frozen | TBD: same topic/source | TBD: score-selected candidate | TBD | Score family boundaries are not frozen | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| B-02 | low | low score family | TBD: exact query not frozen | TBD: same topic/source | TBD: score-selected candidate | TBD | No evidence for controlled score-only change | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| C-01 | clear | one clear candidate | TBD: exact query not frozen | TBD: single authorized candidate | TBD: one candidate | TBD | Candidate-count contrast not instantiated | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| C-01 | equal | two equally plausible candidates | TBD: exact query not frozen | Existing `ppr-query-011` shows Ana/Bruno, but no matched clear arm | TBD: two candidates | `retrieval-f2afa3f534175abec5499067` is only one existing arm | Same topic can be reused only after a clear counterpart is proven | REVIEW REQUIRED |
| C-02 | clear | one person candidate | TBD: exact query not frozen | TBD: single preference association | TBD | TBD | No matched equal/clear pair | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| C-02 | equal | two equally plausible people | Existing query candidate: `I prefer coffee.` | `ppr-source-011-user`, `ppr-source-012-user` | Ana and Bruno source-linked context | `retrieval-f2afa3f534175abec5499067` | Clear counterpart absent; exact query is already used by 5C.4 | REVIEW REQUIRED |
| D-01 | direct | direct neighbor | Existing candidate/query not selected for 5D | Existing corpus contains direct co-occurrences, but no reserved arm | TBD | TBD | Secondary counterpart absent | REVIEW REQUIRED |
| D-01 | secondary | secondary neighbor | TBD: exact query not frozen | Existing graph relation is not exposed as hop metadata | TBD | TBD | Hop distance is not recorded in receipts | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| D-02 | direct | direct source co-occurrence | TBD: exact query not frozen | TBD | TBD | TBD | Controlled two-hop counterpart absent | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| D-02 | secondary | controlled two-hop path | TBD: exact query not frozen | No frozen adjacency/path artifact available | TBD | TBD | Cannot prove hop depth | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| E-01 | hub | hub-connected candidate | Existing AI cases suggest hub behavior, but degree is not recorded | Existing AI source neighborhood | TBD | `retrieval-de5ace7e1a6939ce02001b6a` is observational only | Hub degree unavailable | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| E-01 | non-hub | non-hub candidate | TBD: exact query not frozen | TBD: non-hub graph evidence | TBD | TBD | Comparable relevance and degree not proven | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| E-02 | hub | hub-dense neighborhood | Existing `We are discussing AI.` is a candidate seed only | AI neighborhood in frozen source corpus | TBD | `retrieval-de5ace7e1a6939ce02001b6a` | No formal degree measurement | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| E-02 | non-hub | sparse neighborhood | TBD: exact query not frozen | TBD: sparse graph evidence | TBD | TBD | Sparse/hub contrast not proven | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| F-01 | clean | label/source agreement | Existing clean sources may be candidates, but no reserved pair | TBD: exact source selection required | TBD | TBD | Conflict counterpart absent | REVIEW REQUIRED |
| F-01 | conflict | deliberate label/source conflict | Existing `ppr-query-008` path contains Lisbon label / Madrid source tension | `retrieval-3767fc9294c6a53bb6592618` | TBD: conflict packet must be explicitly bounded | Existing receipt is observational, not a reserved 5D arm | REVIEW REQUIRED |
| F-02 | clean | all sources agree | TBD: exact query not frozen | TBD | TBD | TBD | Conflict counterpart absent | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| F-02 | conflict | one competing source label | Existing `ppr-query-009` retains the same conflict path | `retrieval-cfac1d5389785687393a8f08` | TBD | Existing receipt not reserved for 5D | REVIEW REQUIRED |
| G-01 | statement | declarative statement | Existing corpus has declarative statements, but no reserved arm | TBD | TBD | TBD | Explicit-request counterpart absent | REVIEW REQUIRED |
| G-01 | request | explicit factual question/request | TBD: exact request not frozen | TBD: same proposition/source | TBD | TBD | Query form changes lexical surface unless controlled | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |
| G-02 | statement | conversational topic statement | Existing corpus candidate; exact 5D reservation absent | TBD | TBD | TBD | Request counterpart absent | REVIEW REQUIRED |
| G-02 | request | explicit recall request | TBD: exact request not frozen | TBD: same topic/source | TBD | TBD | No frozen request wording exists | NOT OPERATIONALIZABLE UNDER CURRENT EVIDENCE |

## Pair-Level Review Rules

The following must be checked and signed by a human reviewer before an
amendment hash is computed:

1. Exact query texts are fixed and their UTF-8 SHA-256 values are recorded.
2. Each query resolves to the intended frozen source evidence without creating
   an unknown graph entity or relying on live retrieval.
3. Each contextual arm has a distinct human approval record bound to the exact
   query, receipt, graph snapshot, policy revision, and pair arm.
4. The source packet is byte-identical across a pair except for the declared
   source-consistency manipulation. Any other content difference invalidates
   the pair.
5. Model ID, model-weight fingerprint, prompt fingerprint, sampling
   fingerprint, provider path, K, damping, policy filters, and approval scope
   are byte-identical across a pair.
6. Score differences, hub degree, hop depth, and source conflicts are recorded
   only where frozen evidence proves them. Otherwise the pair is rejected as
   not operationalizable.
7. Expected fields are schemas for capture, not predictions. Actual latency,
   timeout, failure, and raw output are captured independently from utilization
   quality.

## Current Resolution

The original 14-pair design cannot currently be converted into a valid 28-arm
execution amendment. The existing corpus supports useful observational anchors
for `011`, `014`, `008`, and `009`, but it does not provide complete matched
counterparts for all factors. The most material blockers are missing exact arm
queries, absent frozen hop/degree metadata, unavailable sampling fingerprint,
and the lack of reserved pair-level approval/source packets.

### Human Decision

None of the eight `REVIEW REQUIRED` arms currently forms a defensible complete
matched pair under the frozen evidence. They are retained as observational
anchors only. Zero arms are approved for promotion into a Phase 5D execution
amendment at this time.

This is a scientifically valid reduction point: pairs marked `NOT
OPERATIONALIZABLE UNDER CURRENT EVIDENCE` should be removed or replaced only
through an explicit human-reviewed amendment to the design. They must not be
silently manufactured into executable examples.

No formal execution-manifest amendment has been created, no amendment hash has
been computed, and no 5D model output has been generated. The original design
and freeze artifacts remain unchanged.