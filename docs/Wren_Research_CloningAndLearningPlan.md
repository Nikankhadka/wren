> **NAVIGATION:** Frozen source document (v1.0), background only - no ticket requires it except T-040's LEARNINGS rubric (section 4.1). Route implementation work via `docs/INDEX.md`.

# WREN - Market Research, Cloning Strategy & Expert Learning Roadmap
> **Version:** 1.0 | **Companion to:** the four core Wren docs (`Wren_P0P1_CharterAndPRD.md`, `Wren_P3_ArchitectureDoc.md`, `Wren_P3_SprintPlanAndBacklog.md`, `Wren_AGENTS.md`)
> **Purpose:** Ground the whole build in how the real market leaders actually architect these systems, define exactly what Wren is cloning (conceptually - not copying code or IP), and lay out the learning path that turns finishing this project into being genuinely expert-level as an AI Engineer and Forward Deployed Engineer.
> All external claims below are sourced from research conducted July 2026. Figures and competitor details move fast - re-verify before quoting them anywhere public.

---

## ◈ 1. THE MARKET: WHO'S DOING THIS, AND HOW

### 1.1 The category

What you described - a customer-facing agent that replaces browse/search/filter with a conversation that recommends, quotes, and resolves, plus an admin side that monitors and automates - is a real, fast-growing category with two overlapping names: **agentic customer experience (CX)** and **agentic commerce**. The market splits into three tiers:

- **AI-native agentic CX startups** (the ones worth learning from): **Sierra** (Bret Taylor/Clay Bavor, ~$635M+ raised, reportedly serving 40%+ of the Fortune 50), **Decagon** (~$481M raised, ~$4.5B valuation), **Cresta**, **Lorikeet**. These are pure agent platforms built after ChatGPT, and their architecture is the reference design for Wren.
- **E-commerce-specialized CX tools**: **Gorgias**, **Alhena**, **Ada**, **Netomi** - built around Shopify/commerce data, strong on returns/WISMO ("where is my order") and product recommendation.
- **Incumbents adding AI**: **Intercom (Fin)**, **Zendesk**, **Freshworks (Freddy)**, **Salesforce (Agentforce)**, **Kore.ai** - large platforms retrofitting agents onto existing help desks.

### 1.2 What the market says the job actually is

The recurring, high-frequency support jobs across every source are remarkably consistent, which is good news - it means the scope is well-understood and you're building against a known target: order status / WISMO, returns and refunds, product questions and recommendation, and intelligent routing/escalation. Deflection rates of 70-80% are the headline metric the serious players report. Conversion lift from in-chat recommendation (Shopify's own data: a large share of support chats are really purchasing decisions) is the commerce-specific upside.

### 1.3 The one warning the market gives you, and why it validates Wren's scope

One buyer's-guide source notes plainly that teams who try to build their own AI layer generally fail unless they have a strong internal ML/engineering capability. Read that correctly: it is not a reason to avoid building - it is exactly why *having built one* is a valuable, differentiating credential. The thing that's hard to buy off a shelf is the person who has actually done it. That is the entire thesis of this project as a portfolio piece.

---

## ◈ 2. THE REFERENCE ARCHITECTURE (what Sierra and Decagon converge on)

Both category leaders, described in their founders' own words, independently arrive at nearly the same design. This is the architecture Wren clones conceptually. Every element below has a direct, smaller-scale analogue already in your Wren docs - this section is here so you understand *why* each choice exists, which is what separates an engineer who assembled a system from one who understands it.

### 2.1 Goals and guardrails, not scripted steps
Sierra's Agent SDK and Decagon's "Agent Operating Procedures" both reject rigid decision-tree flows. You declare what the agent should achieve and the boundaries it cannot cross (Sierra's canonical example: "orders can only be returned within 30 days of purchase"), and the agent reasons within those bounds. **Wren analogue:** `tenant_config` driving system prompt + enabled tools + escalation thresholds, instead of vertical-specific `if` branches. Your config-driven multi-tenancy *is* this pattern at small scale.

### 2.2 A constellation of models, not one LLM
Sierra explicitly uses 15+ models chosen per task (retrieval, classification, tool-use, tone), orchestrated automatically. Decagon is model-agnostic and picks the best model per job. The point is that the model is not load-bearing on any single version. **Wren analogue:** the model-provider abstraction in Architecture Doc §2.4.3 - you don't need 15 models, but building the seam so a model is a config value, not a hardcode, is the same principle, and you should be able to *explain* why the constellation approach exists.

### 2.3 Supervisory agents that inspect the primary agent's reasoning
This is the single most important pattern in the research, and the one most worth internalizing. Both companies run a second "supervisor" model over the primary agent's output. Taylor's framing: if a reasoning system is right 90% of the time, and a supervisor catching its errors is also right 90% of the time, chaining them gets you to ~99%. Bavor calls it "a little Jiminy Cricket agent looking over the shoulder" - checking: is this factual? is this within policy? is the customer trying to prompt-inject? **Wren analogue:** your Response Validator node (Architecture Doc §2.4.1) is a supervisor. The upgrade this research justifies: make it a genuine reasoning-inspection layer (does the trajectory make sense, is it grounded, is it on-policy), not just a citation/leak check. This is a Tier-1 learning objective (§4).

### 2.4 Deterministic guardrails in code for sensitive actions
Both companies enforce the *critical* steps - refund eligibility, identity checks, the actual price math - in code, never in model judgment. Decagon's phrase: natural-language rules with "key validation steps in code." This is precisely the deterministic-pricing-tool discipline you already flagged (the agent selects rule IDs and quantities; a non-LLM tool computes the dollar total). **Wren analogue:** already core to your design - this research is independent confirmation from two ~$4B+ companies that you had the right instinct. Lean into it hard; it's your safety story.

### 2.5 Simulation and regression testing before shipping
Decagon runs simulations against AI-generated mock personas, unit-tests individual workflow components, and replays historical transcripts against new agent versions to catch regressions. Sierra ships agent changes through CI/CD with GitHub Actions and pre-deployment simulation. **Wren analogue:** your eval harness + CI regression gate (Epics E2/E4/E6, T-034). The upgrade this justifies: add a **conversation-simulation** eval - an LLM plays a customer persona against your agent, and you score the resulting trajectory. This is a Tier-2 stretch that would meaningfully strengthen the portfolio story.

### 2.6 Agent versioning with rollback
Decagon applies CI/CD discipline to agents: version them, roll back if a new version degrades. **Wren analogue:** prompt-as-versioned-config (Architecture Doc references prompt versioning) + tying eval scores to a git SHA. Make the link explicit: every eval run records which prompt/config version produced which scores.

> **The synthesis:** Wren is a faithful, small-scale, single-builder clone of the Sierra/Decagon reference architecture: goals-and-guardrails config, a model abstraction, a supervisor layer, deterministic guardrails on sensitive actions, and simulation/regression eval in CI. You are not copying anyone's code or proprietary IP - you're independently implementing the same publicly-described architectural patterns, which is exactly what learning from the field looks like.

---

## ◈ 3. WHY THIS PROJECT IS ALMOST PERFECTLY AIMED AT YOUR CAREER TARGET

You named two targets: **AI Engineer** and **Forward Deployed Engineer (FDE)**. The research on what those roles actually hire for is striking, because Wren already trains almost the exact stack. This is not a coincidence you should waste.

### 3.1 What the FDE role is (and why it's the highest-leverage role in AI right now)
An FDE is embedded inside a customer's organization to make an AI product actually work in production - "part engineer, part operator, part account owner." The market context: job postings up ~800% year-over-year as of early 2026; both OpenAI and Anthropic launched dedicated FDE units in May 2026; comp ranges widely but sits well above standard SWE bands. The driver: an MIT study found ~95% of enterprise AI pilots produced little measurable impact - not because models are weak, but because of last-mile integration, evaluation, and trust gaps. The FDE is the person hired to close exactly those gaps.

### 3.2 The FDE / AI-Engineer skill stack, mapped to Wren
Every source lists nearly the same stack. Here is that stack with where Wren trains it:

| Skill the role demands | Where Wren builds it |
|---|---|
| RAG pipelines (chunking, vector DBs incl. pgvector, embeddings, reranking) | Epic E1 - hybrid retrieval, the whole ingestion+retrieval subsystem |
| Eval frameworks (LLM-as-judge, golden datasets, regression suites, catching hallucinations/grounding gaps) - repeatedly called the *2026 non-negotiable* | Epics E2, E4, E6 - the three-layer eval harness + CI gate + judge calibration. This is the single most-emphasized FDE skill and it's the centerpiece of Wren. |
| Agent frameworks (LangGraph et al.), multi-step tool-use chains | Epic E3 - the LangGraph supervisor + specialist agents + tools |
| Production observability (logging, latency, token usage, drift) | Epic E6 - Langfuse/OTel tracing + per-tenant cost accounting |
| Security & compliance, deploying in client-controlled infra, data governance | Epic E5 + §2.5/§2.8 - RLS isolation, prompt-injection defense, AWS deploy with least-privilege IAM |
| Full-stack (Python + TypeScript both table-stakes) | The hybrid stack itself - Next.js frontend + FastAPI backend |
| Prompt architecture / structured outputs / guardrails that hold at scale | The whole agent layer + deterministic guardrails |
| Judgment under ambiguity; scoping a vague problem into shipped workstreams | The Venture OS framing + the deliberate WON'T list + this whole scoping exercise |

The two skills Wren *doesn't* naturally train - customer-facing communication and consulting-grade discovery - are the human half of the FDE role. §4.4 addresses how to build those alongside the code so you don't finish with a technical portfolio and a soft-skill gap.

### 3.3 The uncomfortable-but-important caveat
Most FDE listings ask for ~5+ years of production experience. You are targeting mid-level first, which is right. Do not read the FDE research as "apply to OpenAI FDE at the end of this project." Read it as: **this project builds the exact technical foundation the highest-value AI roles are gated on, so pointing your learning at that stack now compounds for years.** The mid-level AI/GenAI Engineer role is the correct next step; the FDE stack is the north star that tells you *which* mid-level role and *which* skills to go deep on.

---

## ◈ 4. THE EXPERT LEARNING ROADMAP

The goal isn't to finish Wren. It's to finish Wren *and be able to defend every decision in it at senior depth.* Building without understanding produces a portfolio you can't survive a follow-up question on. This roadmap runs alongside the 30-day build; each tier maps to build phases and adds a "learn + be able to explain" layer on top of the "make it work" layer.

### 4.1 How to use this roadmap
For each capability you build, you operate at three levels of understanding, and you're not "done" with a topic until you hit level 3:
1. **Make it work** - the ticket passes its acceptance criteria.
2. **Know why this approach** - you can explain the alternatives you didn't pick and why.
3. **Know how it fails** - you can name this component's failure modes and how you'd detect and mitigate them in production.
Level 3 is what interviews for these roles actually probe. Keep a running `LEARNINGS.md` in the repo where, per subsystem, you write a few sentences at each level. That file becomes your interview-prep artifact and doubles as the "documentation discipline" FDEs are explicitly evaluated on.

### 4.2 Tier 1 - Core competencies (must reach level 3 on all of these)

**RAG done right (Weeks 1-2).** Understand: why hybrid beats pure-dense (lexical vs semantic failure modes), what reranking actually does and why cross-encoders differ from bi-encoders, how chunking strategy changes retrieval quality, and why you evaluate retrieval *separately* from generation. Failure modes to be able to discuss: retrieval miss vs generation hallucination vs citation drift, and how you'd tell them apart from metrics alone.

**Agent orchestration (Weeks 2-3).** Understand: why an explicit graph (LangGraph) beats an implicit ReAct loop for reliability and inspectability, what state you thread between nodes and why, when to route vs when to let one agent handle it, and the supervisor pattern from §2.3. Failure modes: infinite tool loops, wrong-tool selection, argument hallucination, and lost context across turns.

**Evaluation engineering (Weeks 1-4, continuous - this is THE non-negotiable).** This is the skill every FDE/AI-Eng source ranks first. Understand deeply: the difference between retrieval eval, generation eval, and trajectory eval; why LLM-as-judge needs calibration against humans and how bias creeps in; what a golden dataset is and how to build one that isn't garbage; why eval must gate CI. Be able to explain: "here's how I know my system works, here's my agreement rate with human labels, here's what my eval *doesn't* catch." If you internalize one thing from this entire project, make it this.

**Deterministic guardrails and safety (Weeks 2-3).** Understand: why the model must never produce the price/refund decision, how spotlighting/delimiting defends against indirect injection, and why HITL is a safety control not a fallback. Failure modes: prompt injection via retrieved content, cross-tenant leakage, unbounded cost. You already have the instincts here - the research (§2.4) confirms them; now be able to articulate them.

**Multi-tenant isolation (Week 1-2).** Understand: why application-layer filtering is insufficient, what RLS actually enforces and at what layer, and how you *prove* isolation rather than assert it. This is your signature security story - be able to walk through the leakage test as a live demonstration.

### 4.3 Tier 2 - Depth that signals seniority (reach level 3 on as many as the clock allows)

- **Supervisor/reflection layer** as a genuine reasoning-inspection agent (§2.3), not just a validator - and be able to explain the 90% × 90% → 99% intuition.
- **Conversation simulation eval** (§2.5) - an LLM persona drives a full conversation, you score the trajectory.
- **Cost engineering** - cost-per-resolution as a first-class metric (Decagon's own pricing is ~per-resolution), and be able to reason about the unit economics of an agent that works but is too expensive to ship.
- **Observability depth** - reading traces to debug a bad trajectory, not just collecting them.
- **The generalization proof** - onboarding tenant #2 by config alone, and being able to explain why config-driven generalization is architecturally non-trivial.

### 4.4 Tier 3 - The FDE human layer (build this deliberately; it doesn't come free with code)

The research is emphatic that FDEs are hired on communication and scoping as much as code. Build these alongside Wren:
- **Write the artifacts.** The eval report, the security write-up, the model card, the `LEARNINGS.md`, the README. FDEs are explicitly evaluated on "documentation discipline that survives your rotation off the engagement." These docs *are* that skill, practiced.
- **Record the walkthrough as if to a customer.** The demo video (T-047) is communication practice - explain the system to a non-expert stakeholder, not to a compiler.
- **Practice the discovery reframe.** For each vertical (e-commerce, repair shop, factory), write the one-paragraph "here's the real problem behind the stated request" summary. That reframing-the-stated-requirement-into-the-real-one muscle is a named FDE technical skill.
- **Do a mock take-home.** FDE loops often include a 24-48h "build an integration against this mock dataset" round. Your tenant #2 onboarding *is* essentially that exercise - treat it like a timed take-home and write up how you approached it.

### 4.5 Foundational study to run in parallel (fill the gaps the build assumes)
If any of these are shaky, shore them up in the first week rather than faking through them, because the build assumes them: Postgres/SQL depth (RLS, indexing, full-text search), the transformer/embedding mental model (enough to reason about why embeddings retrieve what they do), HTTP/streaming/SSE fundamentals (for the chat widget), Docker + AWS basics (ECS, IAM, ALB, VPC), and Git/CI fundamentals. You don't need research-level depth in any of these - you need working fluency and the ability to reason about failure.

---

## ◈ 5. HOW THE VERTICALS RELATE (e-commerce / repair shop / factory)

The customer-side flow you described - "recommend based on need," "phone screen repair under $X," "quote me" - is the same *shape* in all three verticals: **recommend, quote, answer, act, escalate.** That sameness is the whole point and your best story: build the capability once, prove it generalizes by config. The vertical differences live entirely in data and rules, not in agent code:

| | E-commerce (Tenant 1) | Repair shop (Tenant 2 candidate) | Factory (later) |
|---|---|---|---|
| Knowledge corpus | product catalog, policies, FAQ | services + parts + price list, warranty terms | product specs, capabilities, lead times |
| "Quote" means | cart/product total | repair estimate (part + labor) | RFQ / custom quote |
| Order tool | order status, returns | repair-ticket status | order/job status |
| Deterministic math | order/refund totals | part + labor + tax | volume/spec-based pricing |

Recommended path: **e-commerce as Tenant 1** (richest, most legible demo, per your choice), **repair shop as Tenant 2** (the config-only generalization proof - a great fit because "screen repair under $X" is a clean recommend+quote+deterministic-price story). Factory stays a "future work" line in the thesis - naming it shows range without spending clock on it.

---

## ◈ 6. WHAT CHANGES IN THE CORE DOCS AS A RESULT OF THIS RESEARCH

Small, high-leverage upgrades - none of these blow the 30-day clock, and each is justified by a named market-leader pattern:

1. **Upgrade the Response Validator into a real supervisor node** (§2.3) - reasoning inspection, not just citation/leak checks. *(Architecture Doc §2.4.1)*
2. **Add customer-side capabilities to the PRD**: product recommendation ("recommend based on need") and deterministic quoting ("repair under $X") as first-class Knowledge/Order-agent behaviors, with the agent-selects-inputs / code-computes-price split locked in. *(PRD §3.3)*
3. **Add a conversation-simulation eval** as a Tier-2 stretch (§2.5). *(Sprint Plan, stretch)*
4. **Name repair shop as the concrete Tenant 2** and frame it as the FDE-style timed integration exercise. *(PRD S1 / Sprint Plan T-043)*
5. **Add `LEARNINGS.md` as a required repo artifact** (§4.1) and fold it into the definition of done.

Say the word and I'll apply these to the four core docs. I've deliberately not edited them yet, since this reshapes the customer-side scope (recommendation + quoting) and you flagged in the last exchange that the pricing/quoting design is the one hard fork worth a real decision - so that's the one thing I still want you to confirm before I rewrite:

- **Quoting/pricing:** the safe, provable pattern (agent selects priced items/rules; deterministic code computes the total) is what both Sierra and Decagon do and what I'd strongly recommend. Confirm you want that (vs. deferring quoting entirely to keep v1 to recommend-and-answer), and I'll wire recommendation + deterministic quoting through the PRD, Architecture, and Sprint docs.

---

*End of Research, Cloning Strategy & Learning Roadmap. Sources gathered July 2026; re-verify fast-moving competitor and compensation figures before any public use.*
