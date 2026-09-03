# Corpusil frontend redesign

Implemented 31 August 2026. Backend, retrieval, deduplication, fallback logic and API contracts were not changed by this UI work.

## Design decisions

The supplied logo is copied byte-for-byte to `frontend/public/brand/corpusil-logo.png`. A shared wordmark component frames its existing whitespace without recolouring, redrawing or distorting it. The mark is used on sign-in, navigation, the design reference and browser metadata.

| Colour | Value | Purpose |
| --- | --- | --- |
| Forest | `#10201D` | Navigation and primary actions |
| Parchment | `#FAF3EB` | Brand background and warm surfaces |
| Brass | `#785130` | Authority and emphasis |
| Soft gold | `#D1AD77` | Accents against forest |
| Ink | `#17211F` | Reading text |
| Sage | `#65716E` | Supporting text |

Local serif and system sans-serif stacks provide editorial headings and readable controls without external font requests. Reading text is constrained to 76ch. Role layouts differ structurally: citizen guidance, police workflow/register, advocate strategy/folio, and admin governance metrics.

Chat uses semantic Markdown, numbered steps, quotations, expandable authorities, source inspection, copy answer/code/citation/passage, session-local helpfulness controls and regeneration. Loading uses a CSS scales animation inspired by the supplied legal mark. It does not invent live pipeline stage telemetry: real server progress is displayed when available. Reduced-motion CSS disables decorative movement.

## Verification

- `npm run build`: passed, including lint, TypeScript and static export of `/` and `/design-system`.
- `npx tsc --noEmit`: passed.
- `git diff --check -- frontend`: passed.
- Original and public logo copies compare byte-for-byte.
- Signed in using all four documented local demo accounts; verified distinct dashboards and role-specific workspace navigation.
- Citizen Fast research completed against the real backend and rendered its response and citations.
- A real Deep Review displayed the branded loading state. Completion was not used as acceptance evidence: a development hot refresh reset the observing UI while that request was running. Retrieval quality/latency was not re-evaluated in this frontend task.
- Component specimens verified citation expansion, complete citation and answer clipboard content, code and passage copying, helpfulness toggle, regeneration callback and Enter-to-submit.
- Source drawer and command palette open/close, command filtering and Escape handling checked.
- Responsive checks at 390px: component specimen, admin dashboard and admin workspace had no horizontal overflow; mobile navigation opened and closed.
- Administrative tests were read-only. No accounts were created/suspended and no corpus material was uploaded or published.

## Review notes and boundaries

The warm palette, original wordmark and asymmetrical surfaces provide a coherent identity. The role views now organise work differently instead of relying on relabelled dashboard cards. Dense professional forms retain their existing business logic and benefit from a further field-by-field usability pass with real users.

Feedback is local to the mounted response; no persistence endpoint was added. Deep Review latency remains backend-owned. Full native Tauri packaging, exhaustive assistive-technology testing and backend retrieval acceptance were outside this UI verification.

The `/design-system` page is a deliberately labelled, non-submitting component specimen. Its example content is not legal advice or live corpus output.

Screenshots are in `docs/evidence/corpusil-ui/`: `design-system.png`, `chat-loading.png`, `formatted-answer.png`, `answer-actions.png`, `citizen.png`, `police.png`, `advocate.png`, `admin.png`, plus sign-in and responsive checks.
