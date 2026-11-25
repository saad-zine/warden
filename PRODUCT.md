# Warden — Product

## What it is

Warden is an agent reliability platform. It runs AI agents (LangGraph graphs) inside its own backend and wraps them in the control plane production teams need: durable execution with checkpoints, a full trace viewer with replay, human approval gates on risky actions, persistent cross-session memory, and a nightly eval suite that blocks deploys on regression.

## Who it is for

AI engineers and small teams running agents in production (or about to). People who have felt an agent fail silently, loop, lose state on a crash, or take an unsafe action — and found out from a customer, not from their own tooling.

## What it does (the core loop)

- Start a run: pick an agent (Scout, Planner), give it a task.
- Watch it work: every decision, tool call, and gate in the trace.
- Approve the risky step: the agent pauses before CRM writes, sends, and deletes; a human approves or rejects.
- Learn from it: traces feed failure analysis, eval datasets, and the reliability score.
- Block bad deploys: the eval suite replays 8 recorded scenarios against a new agent version; a regression blocks the deploy.

## Brand and voice

- Name: Warden. Guardian/keeper motif. The product is the guardrail, not the agent.
- Voice: direct, honest, measured. Numbers are measured, not claimed. Limitations are stated plainly.
- Visual identity: the Clean design system (see DESIGN.md) — white space, subtle hairline borders, clean rounded shapes, small quiet typography, in the style of Attio and folk. The Warden head mark (black on white) is the logo; the sculk teal accent appears sparingly for active states and highlights. (The earlier RawBlock/brutalist direction was tried and reverted on 2026-11-25 — it did not suit this product.)

## Anti-references (what it is not)

- Not a generic AI dashboard: no purple/blue gradients, no glassmorphism, no rounded "AI slop" cards.
- Not a landing-page toy: this is an operations console. Density and clarity beat decoration.
- No Inter/Roboto/Geist default typography (the detector flags these as overused).
- No decorative images, icons, or illustrations; content and typography do the work.

## Design references (user-supplied)

- Component libraries (direct React components + inspiration): rareui.com, kobra.systems, easyui.site, pinui.xyz, ui.aceternity.com
- UI inspiration / screenshots: mobbin.com, and screenshots the user sends directly (folk, Attio). Do not copy the apps themselves — take the design language (clean white, left sidebar, card-based lists, generous whitespace, small muted text) and apply the Clean design system to it.
- Design authority order: the user's DESIGN.md (Clean) first, then the user's reference sites/screenshots, then Impeccable. Never Muse's own taste.
