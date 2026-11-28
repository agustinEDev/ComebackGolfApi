# ADR-052: No AI Rules Assistant for Now

**Status:** Accepted
**Date:** November 17, 2026
**Context:** Product - AI features
**Author:** Agustín Estévez
**Replaces:** ADR-022 (RAG golf rules assistant), removed on November 17, 2026

---

## Context

ADR-022 (December 2025) planned a golf rules assistant with RAG over the official Rules
of Golf, using Pinecone, OpenAI and Redis. It was never built: none of those services is
in the code or the dependency locks. On 26 October 2026 the AI plan was redone and parked
(the plan itself is kept outside the repository; epic BE #676): a future assistant would
answer only from texts written by the project (the app's own rules, a plain-language
guide that cites and links the official rule numbers, and each organiser's local rules),
because the official text is copyrighted and its terms forbid commercial use. ADR-022 no
longer described any decision in force, so it was deleted.

## Decision

1. **The app has no AI assistant today**, and no AI provider is a dependency.
2. **The parked plan is the reference** if the work starts: own texts only, always citing
   the source, refusing when the texts do not back the answer. Starting it requires a new
   ADR with the chosen architecture.

## Consequences

- No external AI cost, data processing agreement or prompt-injection surface today.
- The old plan (`docs/RAG_IMPLEMENTATION.md`) was removed on 28 November 2026; it remains
  in the git history.
