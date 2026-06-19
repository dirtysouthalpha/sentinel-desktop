# Prompt: Neuralis Brain panel for Sentinel Desktop (for Claude Design)

## What the product is

**Sentinel Desktop** (v17.0) is a vision-driven AI desktop automation agent. You give it a goal in plain English — "open the ticketing app, find all open P1 tickets, summarize each" — and it sees the screen (screenshots + OCR + accessibility tree), moves the mouse, types, clicks native controls, runs terminal/PowerShell/bash/SSH commands, and interacts with any application autonomously. It's used daily by an IT support technician on real servers and workstations. Think of it as a self-driving operator for the desktop.

The app has three modes: a local **cyberpunk HUD GUI** (Python tkinter), a headless API server, and a CLI. This design task is for the **GUI**.

## What I'm adding — the Neuralis Brain panel

Sentinel doesn't just automate — **it learns.** Every task it runs, every fix it lands, every tricky issue it solves gets distilled into the **Neuralis Brain**: a shared memory that *every* agent in the user's fleet reads from and writes to (Sentinel Desktop, Claude Code, opencode, and other AI tools). **The brain learns from all clients and gets smarter with every task.** A fix Sentinel finds on a server at 2am is knowledge Claude Code can recall at noon.

I need a new **"Brain" tab/panel** in the GUI that surfaces this. It should make the user *feel* the brain — neural, alive, growing — and let them see and interact with what's been learned.

## What the panel needs to show and do

The brain exposes 7 operations; the panel should make the important ones visible and interactive:

- **Stats** — a live header: total thoughts stored, thoughts by region (knowledge / context / preference / decision), number of contributing agents/sources, growth over time. This is the "it's getting smarter" dial.
- **Recent thoughts / live feed** — a scrolling stream of the latest memories written by *any* agent in the fleet (each entry: source agent, region, topic, timestamp, a snippet of content). Should feel like a neural activity feed.
- **Recall** — type a topic, see the most relevant stored thoughts ranked. (Topic-keyed lookup.)
- **Search** — free-text search across everything in the brain. Catches things recall misses.
- **Think** — a compose box to manually write a thought to the brain (region selector, topic, content). For when the user wants to teach it directly.
- **(Secondary) Opinions / Fire / Context** — lower priority; can be tucked into an "advanced" section. Fire = activate/stimulate a specific neuron by id. Opinions = what the brain thinks about a topic. Context = a snapshot of current state.

## Visual style — match the existing app, make the brain feel alive

The app is a **cyberpunk HUD**, not a clean modern dashboard. Match this language:

- **Dark-first.** Backgrounds are near-black with a slight color tint. Text is high-contrast. No big white cards, no soft pastels.
- **Neon-on-dark accent system.** The app ships 14 themes (Midnight, Dark, Matrix, Tron, Cyberpunk, Neon, Terminal, Blood, Ocean, Light, Sunset, Paper, Forest, Mono) — the panel must be themeable, defaulting to a neon-cyan / electric-blue primary on near-black. Matrix green and Tron cyan are good reference vibes.
- **Monospace for data, sans for prose.** Timestamps, IDs, stats, code-like content in mono. Descriptions and topics in sans.
- **Glow + scanlines are welcome but tasteful.** The app already has an animated cursor overlay that glides to action locations and pulses. Subtle glow on active/focused elements fits; heavy bloom does not.
- **Dense but legible.** This is a power-user tool. Information density is a feature, not a bug — but hierarchy must be obvious (what's a stat, what's a feed item, what's interactive).
- **The "brain" identity.** This panel is special — it's the killer feature. Give it a signature visual motif that reads as *neural/memory* without being cheesy: consider a subtle node/graph texture, pulsing activity indicators, or a "neuron firing" micro-animation when a new thought streams in. It should feel like the app has a mind that's awake and accumulating.

## Personality / vibe to capture

- One mind across the whole fleet — the panel is a window into shared consciousness, not a local log.
- "It's learning right now" — the live feed should feel alive even when idle (gentle pulse, last-updated timestamps).
- Confident, technical, a little sci-fi. This is the operator's brain.

## Important constraint

I could not pull the exact styling of the existing "Prime dashboard" brain view to reference (that server is offline during this design pass). So design to the **app's established cyberpunk HUD language** described above and to standard neural/brain-dashboard conventions; the goal is a panel that looks native to Sentinel Desktop and makes the shared-memory concept immediately legible. Assume I'll refine toward an exact fleet-wide visual match later.

## Deliverable I want from you

A design spec + mockup for the Brain panel: layout, the stats header, the live feed, the recall/search area, the compose box, theming notes, and the "brain is alive" signature motif. Show me how it looks in at least the default neon-cyan-on-black theme. Call out any state transitions (loading, empty brain, error/reconnecting, new-thought-arrived).

