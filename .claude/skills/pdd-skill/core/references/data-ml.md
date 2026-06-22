# PDD Reference: Data / ML / AI Projects

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for data engineering, machine learning, and AI pipeline projects.

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Is this data engineering, ML modeling, AI pipeline, or a combination?
- What's the primary language and environment? (Python, Jupyter, SQL, Spark, etc.)
- What data sources are involved? (databases, APIs, files, streams)
- How is data stored and accessed? (S3, GCS, data warehouse, feature store)
- Is there a pipeline orchestrator? (Airflow, Prefect, Luigi, dbt, Dagster)
- For ML: what framework? (PyTorch, TensorFlow, scikit-learn, HuggingFace, XGBoost)
- How are experiments tracked? (MLflow, Weights & Biases, Neptune, local)
- How is the model or pipeline deployed? (batch, real-time API, embedded)
- What are the evaluation metrics? (accuracy, F1, RMSE, custom business metric)

**Distributed compute:**
- Distributed compute framework? (Spark, Flink, Dask, Ray, none)
- If Spark: deployment (Databricks, EMR, Dataproc, self-managed)?
- Table format? (Delta Lake, Iceberg, Hudi, Parquet files, warehouse-native)
- Catalog / governance layer? (Unity Catalog, Hive Metastore, AWS Glue, none)
- Cost model awareness? (DBUs, compute credits, spot/preemptible instances)
- Interactive notebooks in production? (Databricks notebooks, Jupyter, no — .py only)

**MLOps:**
- Model registry? (MLflow, SageMaker Model Registry, Vertex AI, none)
- Feature store? (Feast, Tecton, Databricks Feature Store, SageMaker, none)
- Model serving infrastructure? (SageMaker endpoints, Vertex AI, BentoML, TorchServe, custom API)
- Model monitoring? (Evidently, WhyLabs, Arize, custom, none)
- Deployment strategy? (shadow mode, A/B testing, canary, blue-green, direct swap)
- Retraining trigger? (scheduled, drift-detected, manual)

### Extended `pdd/context/project.md` sections for data/ML

```markdown
## Data
- Sources:
- Storage:
- Volume / frequency: (e.g. 10M rows daily batch, or real-time stream)
- Data quality issues known:

## Pipeline
- Orchestrator:
- Schedule / trigger:
- Idempotency requirement: yes / no

## Modeling (if applicable)
- Framework:
- Model type / architecture:
- Training data location:
- Evaluation metrics:
- Experiment tracker:

## Deployment
- Serving pattern: batch / real-time API / embedded
- Latency requirements:
- Monitoring approach:

## Distributed Compute (if applicable)
- Framework: (Spark, Flink, Dask, Ray)
- Cluster config: (instance types, min/max workers, autoscaling policy)
- Deployment platform: (Databricks, EMR, Dataproc, self-managed)
- Table format: (Delta Lake, Iceberg, Hudi, Parquet files)
- Catalog: (Unity Catalog, Hive Metastore, AWS Glue)
- Cost constraints: (budget per job, spot instance policy)

## MLOps (if applicable)
- Model registry: (MLflow, SageMaker, Vertex AI)
- Feature store: (Feast, Tecton, Databricks Feature Store, SageMaker)
- Serving infrastructure: (SageMaker endpoints, Vertex AI, BentoML, TorchServe, custom API)
- Monitoring and drift detection: (Evidently, WhyLabs, Arize, custom)
- Promotion pipeline: (dev → staging → production)
- Rollback strategy: (revert to previous model version, traffic shift)
- Retraining policy: (scheduled, drift-triggered, manual)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Data / ML Conventions

## Project structure
- notebooks/ — exploration only, never production code
- src/ — production pipeline and model code
- data/ — raw/, processed/, features/ (never commit raw data)
- models/ — serialized model artifacts
- configs/ — hyperparameters and pipeline config (YAML or JSON)
- tests/ — unit and integration tests for pipeline steps

## Code standards
- All production code in .py files — not notebooks
- Notebooks are for exploration and documentation only
- Every pipeline step is a pure function where possible
- Functions accept explicit inputs and return explicit outputs — no global state

## Reproducibility
- All randomness seeded explicitly
- All dependencies pinned in requirements.txt or pyproject.toml
- Data transformations versioned alongside code
- Config-driven: hyperparameters and paths in config files, not hardcoded

## Pipelines
- Each step idempotent — running twice produces the same result
- Intermediate outputs saved to allow reruns from any step
- Failed steps fail loudly — no silent data corruption
- Data validation at pipeline entry and exit points

## Experiments
- Every run logged to [MLflow / W&B / local tracker]
- Log: params, metrics, artifacts, and the git commit hash
- Never overwrite a previous experiment run

## Data handling
- Never modify raw data in place — always write to a new output path
- PII fields documented and masked before any logging or sharing
- Schema validated on ingest using [Great Expectations / Pydantic / pandera]

## Distributed compute (if applicable)
- Never call collect() or toPandas() on unbounded datasets — aggregate first
- Partition by commonly filtered columns (date, region, etc.)
- Avoid UDFs when native Spark/Flink functions exist — UDFs break optimization
- Broadcast small lookup tables explicitly
- Set shuffle partition count based on data volume, not defaults
- Cache/persist only when reused — unpersist after use
- Use Delta Lake / Iceberg merge operations instead of read-rewrite patterns

## MLOps (if applicable)
- Models are promoted through stages (dev → staging → production), never deployed directly
- Every production model has a rollback target — the previous blessed version
- Feature definitions live in the feature store, not duplicated in training and serving code
- Model monitoring runs on every prediction batch or continuously for real-time — not just at deploy
- Retraining pipelines are automated and triggered by drift detection or schedule, not ad hoc
- A/B tests and shadow deployments require a success metric and a decision deadline
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New pipeline step

```markdown
# Prompt: <StepName> Pipeline Step

## Task
Create a pipeline step `<step_name>` that <transforms / filters / aggregates> <data>.

## Input
- Source: <file path pattern / table / stream>
- Schema: <field names and types>
- Volume: <approximate row count or size>

## Transformation logic
- <describe what happens to the data step by step>
- <edge cases: nulls, duplicates, out-of-range values>

## Output
- Destination: <output path / table>
- Output schema: <field names and types>
- Partitioning: <by date / by key / none>

## Constraints
- Step must be idempotent
- Log row counts at input and output
- Raise an exception (don't silently continue) if input schema doesn't match expected
- Use [pandas / Spark / dbt / Polars — match existing stack]
```

### Model training script

```markdown
# Prompt: <ModelName> Training Script

## Task
Write a training script for a <model type> that predicts <target>.

## Data
- Training data path: <path>
- Features: <list of feature columns>
- Target: <target column>
- Train/val/test split: <ratios>

## Model
- Framework: <PyTorch / sklearn / XGBoost>
- Architecture / algorithm: <describe or leave open>
- Hyperparameters: <list with defaults — these will come from config>

## Evaluation
- Primary metric: <metric>
- Additional metrics: <list>
- Log all metrics and params to <tracker>

## Outputs
- Save model artifact to: models/<model-name>-<run-id>/
- Save evaluation report to: reports/<model-name>-<run-id>.json

## Constraints
- Seed all randomness for reproducibility
- Config-driven — no hardcoded hyperparameters
- Script must be runnable from CLI: `python train.py --config configs/train.yaml`
```

### Distributed data pipeline step

```markdown
# Prompt: <StepName> Distributed Pipeline Step

## Task
Create a distributed pipeline step `<step_name>` that <transforms / filters / aggregates> <data> using <Spark / Flink / Dask / Ray>.

## Input
- Source: <table / path / stream — format: Delta, Iceberg, Parquet, CSV>
- Schema: <field names and types>
- Volume: <approximate size — rows, GB, partitions>

## Transformation logic
- <describe what happens to the data step by step>
- <edge cases: nulls, duplicates, late-arriving data, skewed keys>

## Distributed concerns
- Partition strategy: <partition by which columns, target partition size>
- Shuffle handling: <joins that require shuffle — can any be broadcast?>
- Data skew: <known skew keys, mitigation strategy — salting, pre-aggregation>
- Caching: <which intermediate DataFrames to persist, when to unpersist>

## Output
- Destination: <output table / path — format>
- Write mode: <overwrite, append, merge/upsert>
- Table maintenance: <OPTIMIZE, Z-ORDER, VACUUM — if Delta/Iceberg>

## Cost and performance
- Cluster sizing: <expected instance types, worker count>
- Estimated runtime: <approximate, for monitoring alerts>
- Cost budget: <max acceptable cost per run>

## Constraints
- Step must be idempotent
- No collect() or toPandas() on full dataset — aggregate first
- Use native functions — no Python UDFs unless unavoidable
- Log row counts, partition counts, and runtime at input and output
- Raise on schema mismatch — don't silently continue
```

### Model deployment pipeline

```markdown
# Prompt: <ModelName> Deployment Pipeline

## Task
Create a deployment pipeline that promotes <model> from training through staging to production serving.

## Model Registration
- Registry: <MLflow, SageMaker, Vertex AI>
- Metadata: <model version, training data version, metrics, git commit, params>
- Artifacts: <model binary, preprocessing pipeline, feature schema>

## Promotion Pipeline
- Stages: dev → staging → production
- Stage gate criteria: <metric thresholds, validation tests, approval process>
- Staging validation: <run against holdout set, shadow traffic, integration tests>
- Promotion mechanism: <manual approval, automated on metric pass, both>

## Serving
- Infrastructure: <SageMaker endpoint, Vertex AI, BentoML, TorchServe, custom API>
- Deployment strategy: <shadow mode, A/B test, canary, blue-green, direct swap>
- Scaling: <autoscaling config, min/max instances, concurrency>
- Latency requirement: <p50, p99 targets>

## Monitoring
- Prediction drift: <method — PSI, KL divergence, KS test — threshold and alert>
- Data quality: <input feature validation, missing values, out-of-range>
- Performance metrics: <accuracy/F1/RMSE on labeled feedback, if available>
- Alerting: <where alerts go, escalation path>

## Rollback
- Trigger: <drift threshold exceeded, error rate spike, manual>
- Mechanism: <revert to previous model version, traffic shift>
- Verification: <confirm rollback model is serving, metrics stabilize>

## Constraints
- Feature parity between training and serving — no training/serving skew
- Model artifacts must be reproducible from logged params and data version
- Rollback must complete within <time budget>
- Monitoring must be active before any production traffic

## Output format
- Model registration script
- Promotion pipeline (CI/CD config or orchestrator DAG)
- Serving configuration and deployment script
- Monitoring setup (drift detection, alerts)
- Rollback procedure and script
- Tests: promotion gate validation, rollback verification, serving latency check
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Correctness**
- [ ] Data transformations produce expected output on a sample?
- [ ] Edge cases handled: nulls, empty input, schema drift?
- [ ] No silent data loss (rows dropped without logging)?

**Reproducibility**
- [ ] Random seeds set explicitly?
- [ ] No hardcoded paths — all via config or parameters?
- [ ] Dependencies pinned?

**Pipeline integrity**
- [ ] Each step idempotent?
- [ ] Input schema validated before processing?
- [ ] Output schema validated after processing?
- [ ] Intermediate outputs persisted for reruns?

**Data hygiene**
- [ ] Raw data never modified in place?
- [ ] PII handled and masked appropriately?
- [ ] No sensitive data in logs or experiment tracker?

**ML-specific**
- [ ] Train/val/test split correct — no leakage?
- [ ] Evaluation metrics appropriate for the problem type?
- [ ] Experiment logged with params, metrics, and git hash?
- [ ] Model artifact saved with version information?

**Performance**
- [ ] Vectorized operations used instead of row-level loops?
- [ ] Memory usage reasonable for expected data volume?
- [ ] Long-running steps parallelized where possible?

**Distributed compute** (if applicable)
- [ ] No collect() or toPandas() on large datasets without prior aggregation?
- [ ] Partition strategy specified and appropriate for query patterns?
- [ ] No unnecessary shuffles (repartition, groupBy without prior filter)?
- [ ] Broadcast joins used for small lookup tables?
- [ ] No Python UDFs where native functions would work?
- [ ] Cluster resources sized for the data volume?
- [ ] Job cost estimated and within budget?
- [ ] Table format operations used correctly (MERGE, OPTIMIZE, Z-ORDER)?

**MLOps** (if applicable)
- [ ] Model registered in model registry with version and metadata?
- [ ] Promotion pipeline tested (dev → staging → production)?
- [ ] Rollback mechanism verified — can revert to previous model version?
- [ ] Feature parity between training and serving (no training/serving skew)?
- [ ] Monitoring configured for prediction drift and data quality?
- [ ] A/B test or shadow deployment has success criteria and decision deadline?
- [ ] Retraining pipeline triggered correctly (schedule or drift threshold)?
- [ ] Model artifacts reproducible from logged params and data version?
