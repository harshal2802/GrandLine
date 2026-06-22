# PDD Reference: Security / Pentesting Tools

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for security tool development projects (scanners, fuzzers, exploit frameworks, detection engines, SIEM integrations, defensive utilities, and similar offensive or defensive security tooling).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Offensive, defensive, or dual-use tool?
- Target domain (web app, network, binary, cloud, mobile)?
- Language (Python, Go, Rust, C)?
- Does it integrate with existing frameworks (Metasploit, Burp, nuclei)?
- Compliance context (pentest engagement, bug bounty, internal red team, CTF)?
- Output format requirements (SARIF, JSON, CSV, SIEM-compatible)?
- Does it handle sensitive data (credentials, PII, exploit payloads)?
- Rate limiting and target safety considerations?

### Extended `pdd/context/project.md` sections for security / pentesting tools

```markdown
## Tool Classification
- Type: (scanner, fuzzer, exploit framework, detector, SIEM integration, utility)
- Offensive / defensive / dual-use:
- Target domain: (web app, network, binary, cloud, mobile, API)
- Intended operators: (pentesters, SOC analysts, developers, red team, blue team)

## Legal and Ethical Boundaries
- Authorized use context: (pentest engagement, bug bounty, internal red team, CTF, research)
- Scope restrictions: (target whitelist, out-of-scope systems, rate limits)
- Responsible disclosure policy:
- Legal disclaimer requirements:
- Data handling obligations: (GDPR, PCI-DSS, client contracts)

## Detection and Coverage
- What it detects / exploits: (vulnerability classes, CVE patterns, misconfigurations)
- Known limitations: (what it cannot detect, blind spots)
- False positive tolerance: (acceptable FP rate for the use case)
- False negative tolerance: (acceptable FN rate for the use case)
- Evasion considerations: (if offensive — how it handles WAF/IDS; if defensive — how it resists evasion)

## Integration Points
- CI/CD integration: (GitHub Actions, GitLab CI, Jenkins)
- SIEM integration: (Splunk, Elastic, Sentinel — log format, transport)
- Ticketing integration: (Jira, ServiceNow — auto-create findings)
- Framework integration: (Metasploit, Burp, nuclei, Semgrep)
- API: (REST, gRPC, CLI — for automation and orchestration)

## Sensitive Data Handling
- Credentials: (how discovered creds are stored, masked, and rotated)
- Exploit payloads: (storage, access control, sanitization)
- PII: (how PII in scan results is handled)
- Findings: (encryption at rest, access control, retention policy)
- Logs: (what is logged, what must never be logged)

## Reporting Format and Standards
- Output format: (SARIF, JSON, CSV, HTML, PDF)
- Vulnerability standards: (CVE, CWE, CVSS scoring)
- Compliance mapping: (OWASP Top 10, NIST, PCI-DSS, CIS Benchmarks)
- Report audience: (technical team, management, client deliverable)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Security / Pentesting Tool Conventions

## Safe Defaults
- All tools default to dry-run / safe mode — destructive or intrusive actions require explicit opt-in
- Rate limiting enabled by default — configurable but never zero
- Scope enforcement built-in — tools refuse to operate on out-of-scope targets
- Credential and sensitive data masking in all output and logs by default
- Verbose mode off by default — noisy output only when explicitly requested

## Input Handling and Protocol Parsing
- Never trust input from targets — all received data is potentially adversarial
- Use established parsing libraries for protocols (HTTP, TLS, DNS, SMTP) — don't hand-roll parsers
- Fuzz your own parsers — if the tool parses network data, test with malformed input
- Set timeouts on all network operations — hanging on a slow target is a denial-of-self
- Handle binary data safely — no assumptions about encoding, null termination, or alignment

## Detection Quality (Defensive Tools)
- Every detection rule must have a known-good test case (true positive) and a benign test case (true negative)
- Track false positive rate as a first-class metric — unusable tools get disabled
- Include confidence scores with findings — not all detections are equal
- Provide remediation guidance with every finding, not just the vulnerability name
- Version detection rules independently — a rule update shouldn't require a full tool release

## Offensive Tool Ethics
- Include a legal disclaimer and acceptable use policy in README and --help output
- Log all actions taken against targets — full audit trail for engagement reports
- Support scope files (target whitelist) and refuse to operate without one in non-CTF mode
- Implement --dry-run that shows what would be done without doing it
- Never exfiltrate data beyond what's needed to prove the vulnerability

## Error Handling
- Network errors are expected, not exceptional — retry with backoff, don't crash
- Partial results are valuable — save progress incrementally, don't lose findings on crash
- Distinguish between tool errors and target errors in output
- Exit codes must be meaningful — 0 for clean run, 1 for findings, 2 for tool error
- Never expose internal stack traces to the operator unless in debug mode

## Testing
- Maintain a corpus of known-vulnerable targets (Docker containers, intentionally vulnerable apps)
- Measure false positive and false negative rates against the corpus in CI
- Fuzz the tool's own input parsing with malformed data
- Test rate limiting actually works — verify request counts against a mock target
- Test against adversarial targets that respond with malicious payloads
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New scanner or detection rule

```markdown
# Prompt: <VulnerabilityClass> scanner / detection rule

## Task
Create a scanner (or detection rule) for <vulnerability class> (e.g., SQL injection, SSRF, misconfigured S3 buckets, exposed secrets).

## Target
- Domain: <web app, cloud config, network service, source code>
- Input: <URLs, IPs, config files, source code paths, CIDR ranges>
- Protocol: <HTTP, DNS, TLS, SSH, cloud API>

## Detection Logic
- What indicates the vulnerability: <specific condition, response pattern, config value>
- Known true positive examples: <concrete examples that should trigger>
- Known true negative examples: <benign cases that should not trigger>
- Confidence levels: <high / medium / low — what distinguishes them>

## Constraints
- False positive rate target: <e.g., <5% against known-good corpus>
- Rate limiting: <max requests per second, default and configurable>
- Timeout per target: <max time before moving on>
- Safe by default: <no destructive payloads, no data exfiltration>
- Must handle: target down, slow response, unexpected content type, connection reset

## Output
- Finding format: <SARIF, JSON, structured log — include CWE, CVSS, remediation>
- Severity classification: <critical, high, medium, low, informational>
- Remediation guidance per finding

## Output format
- Scanner implementation
- Detection rule / signature definition
- True positive and true negative test cases
- False positive rate measurement script
- Example output for a detected vulnerability
```

### Fuzzer or harness

```markdown
# Prompt: <Target> fuzzer

## Task
Create a fuzzing harness for <target> (e.g., file parser, network protocol handler, API endpoint, deserialization routine).

## Target
- Component: <function, endpoint, parser, protocol handler>
- Input format: <binary, JSON, protobuf, custom — provide spec or examples>
- Language: <target language and fuzzing framework — AFL, libFuzzer, go-fuzz, Atheris>

## Fuzzing Strategy
- Seed corpus: <known-good inputs to start with>
- Mutation strategy: <bit-flip, grammar-aware, protocol-aware, dictionary-based>
- Coverage goals: <specific code paths, error handlers, edge cases to reach>
- Crash triage: <how to deduplicate and classify found crashes>

## Invariants
- <conditions that must always hold — e.g., "never segfault", "output size <= input size * 2", "always returns valid JSON or error">
- <resource limits — memory, CPU time, file descriptors>

## Constraints
- Harness must be hermetic — no network, no filesystem writes outside temp
- Must run under sanitizers (ASAN, MSAN, UBSAN) without false positives
- Crashes must be reproducible from the saved input
- Corpus minimization strategy for CI integration

## Output format
- Fuzzing harness implementation
- Seed corpus (5-10 representative inputs)
- Build and run instructions
- Crash triage and deduplication notes
- CI integration configuration
```

### SIEM integration or detection pipeline

```markdown
# Prompt: <DataSource> SIEM integration

## Task
Build a detection pipeline that ingests <data source> (e.g., CloudTrail logs, network flow data, endpoint telemetry) and produces alerts for <threat category>.

## Data Source
- Source: <CloudTrail, VPC Flow Logs, Sysmon, audit.log, custom app logs>
- Format: <JSON, CEF, syslog, parquet, custom>
- Volume: <events per second / day — sizing context>
- Transport: <S3, Kafka, syslog, API pull, agent push>

## Detection Rules
- <rule name — condition — severity — MITRE ATT&CK mapping>
- <for each rule: what triggers it, what's a known false positive>
- Correlation rules: <multi-event patterns, time windows>
- Threshold-based rules: <N events in M minutes>

## Alert Quality
- Each rule must have a documented false positive scenario and suppression strategy
- Alert fatigue budget: <max alerts per day before analysts ignore the tool>
- Enrichment: <what context to add — GeoIP, threat intel, asset inventory>
- Severity assignment criteria:

## Constraints
- Processing latency: <real-time, near-real-time, batch — SLA>
- Must handle: malformed logs, missing fields, clock skew, duplicate events
- Retention: <how long to keep raw vs. aggregated data>
- Access control: <who can see alerts, modify rules, access raw data>

## Output format
- Ingestion and parsing module
- Detection rules (SIGMA, SPL, KQL, or custom format)
- Alert schema with enrichment fields
- Test cases: simulated attack producing true positive, benign activity producing no alert
- Runbook template for each alert type
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Safety and ethics**
- [ ] Safe defaults enabled (dry-run, rate limiting, scope enforcement)?
- [ ] Legal disclaimer and usage terms present in README and help output?
- [ ] No hardcoded credentials, API keys, or sensitive data in source?
- [ ] Sensitive data (discovered creds, PII) masked in output and logs?
- [ ] Scope enforcement prevents operation on unauthorized targets?
- [ ] Audit trail logs all actions taken against targets?

**Detection quality** (scanners / defensive tools)
- [ ] False positive rate measured against a known-good corpus?
- [ ] False negative rate measured against a known-vulnerable corpus?
- [ ] Confidence scores included with findings?
- [ ] Remediation guidance provided for each finding type?
- [ ] Findings tagged with CWE, CVSS, or relevant classification?
- [ ] Detection rules versioned independently from tool releases?

**Input robustness**
- [ ] Handles malformed or adversarial input without crashing?
- [ ] Protocol parsing uses established libraries, not hand-rolled?
- [ ] Timeouts set on all network operations?
- [ ] Binary data handled safely (no encoding assumptions)?
- [ ] Tool's own parsers fuzz-tested?

**Operational fitness**
- [ ] Rate limiting works and is configurable?
- [ ] Partial results saved on crash or interruption?
- [ ] Exit codes meaningful (0 clean, 1 findings, 2 tool error)?
- [ ] Output format conforms to spec (SARIF, JSON schema, etc.)?
- [ ] Integrates cleanly with target workflow (CI, SIEM, ticketing)?
- [ ] Performance acceptable at expected scale (targets, events, rules)?

**Offensive tool specifics** (if applicable)
- [ ] --dry-run mode available and accurate?
- [ ] Scope file / target whitelist enforced?
- [ ] No unnecessary data exfiltration beyond proof of vulnerability?
- [ ] Payload safety — no unintended damage to targets?
- [ ] Actions logged for engagement reporting?
