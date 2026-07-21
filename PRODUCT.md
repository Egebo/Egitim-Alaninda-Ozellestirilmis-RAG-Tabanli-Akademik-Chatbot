# Product

## Register

product

## Platform

web

## Users

The primary audience is the thesis jury and portfolio visitors (recruiters, other engineers) evaluating this as a bitirme projesi and case study — they judge it in a single short session, so the interface itself has to read as production-grade within seconds. The secondary audience is a hypothetical university student using the assistant for real: asking about courses, grades, advisors, or uploaded documents. The interface is designed for the primary audience's scrutiny while staying fully functional for the secondary audience's actual workflow.

## Product Purpose

An academic advisor chatbot that combines RAG (uploaded documents) and Text-to-SQL (a demo academic database) behind a single conversational interface, routed automatically by an intent-classifying orchestrator. It exists to demonstrate that the underlying system — multi-tool orchestration, self-correcting SQL generation, document retrieval, web search fallback — is real and working, not a mockup. Success is a jury member or recruiter concluding, from the UI alone, that this is a serious, working piece of engineering, and a hypothetical student being able to ask a natural question and get a useful answer without friction.

## Positioning

An academic advisor that feels as effortless as ChatGPT on the surface, while a real multi-tool orchestrator (SQL, vector search, web) works underneath — and shows its work.

## Brand Personality

Sade ve güvenilir. Academic seriousness expressed through restraint, not decoration: minimal, ChatGPT-familiar chat surface, nothing competing for attention with the conversation itself. The one place personality is allowed to show is the live step-indicator — it should feel confident and transparent ("here's exactly what I'm doing"), not playful or cute.

## Anti-references

The current interface: a 3-column layout (sidebar + chat + a separate documents panel) visible simultaneously, and the general feeling of too much competing for attention at once. The redesign must never reintroduce a standing documents panel — document handling lives inside the conversation.

## Design Principles

- **Clarity at a glance** — one primary surface (the conversation) at any given moment; nothing else competes with it for attention.
- **Polish reads as credibility, not decoration** — every visual choice should reinforce "this is real engineering," never ornament for its own sake.
- **Process transparency** — the orchestrator's live step-by-step progress (which tool is running) stays visible during generation; it's proof the system is doing real multi-tool work, not a black box.
- **Chat is the first-class citizen** — RAG document upload/management is embedded in the composer and message stream, never a separate standing panel.

## Accessibility & Inclusion

Standard web accessibility: full keyboard navigability, WCAG AA contrast minimums, visible focus states. No additional accommodation requirements specified.
