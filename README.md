# Aetheris

> This repo was built by me to understand system architecture decisions for high-volume data pipelines with AI-based decision layers.

Aetheris is a distributed anomaly-detection and decision pipeline for high-volume financial events.

The project began as a single subscriber demo and evolved into a multi-stage system with:
- fast edge anomaly detection
- buffered orchestration
- multi-agent consensus decisions

## What I actually built

- Streamed `50,000` transactions from CSV into MQTT (`aetheris-ingestion/publish.js`)
- Built distributed edge processors (`aetheris-ingestion/subscribe.js`) with:
  - per-account rolling window (`100` points)
  - Z-score anomaly detection
  - deterministic account-to-node routing
- Published only anomalies to `aetheris/exceptions`
- Created a separate Python intelligence service (`aetheris-agents`) with:
  - Redis priority buffering (`immediate` vs `batch`)
  - LangGraph orchestration
  - 3-agent vote (`Analyst`, `Auditor`, `Strategist`)
  - 2/3 consensus output to `aetheris/commands`
- Added queue and decision metrics logging

## Why this architecture

- Edge computations are cheap and fast; LLM decisions are slow and expensive.
- So the pipeline filters early and escalates only exceptions.
- Redis sits between fast producers and slow agents to absorb bursts.
- Multi-agent vote reduces single-model decision brittleness.

## Build timeline (what changed, why it changed)

1. **Raw pub/sub sanity check**
- Published CSV rows to MQTT and subscribed to confirm transport.
- Goal: prove ingest works before adding intelligence.

2. **Single-node anomaly detector**
- Added rolling Z-score logic to subscriber.
- First issue: no anomalies at high threshold because synthetic data range was tight.
- Fix: switched from global baseline to per-account history.

3. **Initial multi-node attempt**
- Ran multiple subscribers to mimic mesh behavior.
- Issue: all nodes did duplicate work (redundancy, not parallelism).

4. **Workload partitioning iteration**
- Tried prefix/range splits, then modulo hash routing.
- Learned: balance and state consistency matter more than "just more nodes".

5. **Node count reasoning**
- Discussed why not 100 nodes: broker fanout, coordination overhead, low marginal gain.
- Settled on a practical small-node setup for this workload.

6. **Intelligence layer separation**
- Moved agents out of ingestion service into separate Python service.
- Reason: clearer ownership, easier scaling, cleaner architecture.

7. **Prompt-only multi-agent -> real orchestrated flow**
- Replaced simple role prompts with structured orchestrator + tool execution pattern.
- Added LangGraph state flow and explicit consensus step.

8. **Buffering and backpressure control**
- Direct processing showed queue lag under sustained anomaly volume.
- Added Redis streams with scoring and priority routing.

9. **Observability pass**
- Added periodic metrics to see queued vs processed and decision mix.
- Reason: needed objective runtime visibility, not just logs.

## Real problems faced

- **Stateful anomaly detection design**: global Z-score looked mathematically fine but behaviorally wrong; per-account baselines were required.
- **Work partition correctness**: ensuring the same account consistently maps to the same node to preserve rolling state.
- **Throughput mismatch**: edge layer can emit faster than LLM layer can decide.
- **Backpressure and queue growth**: even with healthy processing, backlog still grows under sustained input.
- **Priority policy tuning**: choosing suspicion threshold (`immediate` vs `batch`) changes cost/latency trade-offs.
- **Node scaling trade-off**: more nodes improved parallelism only up to broker/network overhead limits.
- **Batch semantics confusion**: increasing queue read size alone did not improve decision throughput; true semantic batching is still pending.
- **Explainability vs speed**: richer multi-agent reasoning increases latency and operational cost.
- **Data realism**: synthetic dataset distribution affects anomaly rates and threshold behavior.
- **Operational coordination**: many moving pieces (EMQX, Redis, Mongo, Node services, Python service) increased runbook complexity.

## Repo layout

```text
Aetheris/
  data/                    # synthetic finance dataset (50k+ rows)
  SRS.md                   # requirements/spec notes
  problemsfaced            # rough notes captured during build
  aetheris-ingestion/      # Node.js stream + edge detection
  aetheris-agents/         # Python uv LangGraph intelligence layer
```

## Tech stack

- Edge/Ingestion: Node.js, MQTT.js, csv-parser
- Broker: EMQX
- Intelligence: Python 3.11, uv, LangGraph, langchain-groq
- Buffer/state: Redis Streams
- Historical context tool: MongoDB

## Run end-to-end

### 1) Start infrastructure

```bash
docker run -d --name emqx -p 1883:1883 -p 18083:18083 emqx/emqx:5.7
docker run -d --name redis -p 6379:6379 redis:7
docker run -d --name mongo -p 27017:27017 mongo:7
```

### 2) Start edge nodes

From `aetheris-ingestion`:

```bash
npm install
node subscribe.js -- --node-name=EdgeNode1 --node-count=5
node subscribe.js -- --node-name=EdgeNode2 --node-count=5
node subscribe.js -- --node-name=EdgeNode3 --node-count=5
node subscribe.js -- --node-name=EdgeNode4 --node-count=5
node subscribe.js -- --node-name=EdgeNode5 --node-count=5
```

### 3) Start intelligence service

From `aetheris-agents`:

```bash
uv sync
copy .env.example .env
# set GROQ_API_KEY and GROQ_MODEL
uv run python main.py
```

For low-cost testing:

```text
GROQ_MODEL=llama-3.1-8b-instant
```

### 4) Replay stream

From `aetheris-ingestion`:

```bash
node publish.js
```

## Current limitations

- Batch queue still processes item-by-item (not semantic grouped decisions yet).
- LLM latency dominates throughput.
- Orchestrator is single-process in current form.
- Historical tooling assumes Mongo collection readiness.

## Next upgrades

1. Semantic batching (group by account + time window)
2. Multiple Redis consumer workers
3. Rule-based triage before LLM (top-risk-only escalation)
4. Prometheus/Grafana instrumentation
5. Rust/Wasm edge runtime migration path

## Final note

This repo shows the full engineering thought process: build fast, measure bottlenecks, and refactor architecture where needed instead of forcing a one-shot design.

## Data source

Thanks to this dataset for powering the project experiments:
https://www.kaggle.com/datasets/testdatabox/finance-fraud-and-loans-dataset-testdatabox
