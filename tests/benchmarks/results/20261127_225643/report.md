# architekton benchmark report

**Run:** `20261127_225643` &nbsp; **Date:** 2026-11-27 22:56 &nbsp; **Mode:** both &nbsp; **Duration:** 115.3m

---

**33 passed** · **1 failed**

---

## Classification

> Verifies architekton selects the right model family for a prompt without running a full session.

| ID | Test | Expected | Selected | Score | Result | Time |
|----|------|----------|----------|-------|--------|------|
| C01 | Simple file rename task | haiku | haiku | 0.23 | ✓ | 0.08s |
| C02 | Code review task | sonnet | sonnet | 0.62 | ✓ | 0.06s |
| C03 | Architectural design task | opus | opus | 0.74 | ✓ | 0.06s |
| C04 | Data analysis task | sonnet | sonnet | 0.35 | ✓ | 0.08s |
| C05 | Show files (light signal) | haiku | haiku | 0.23 | ✓ | 0.07s |
| C06 | Security exploit analysis (two heavy signals) | opus | opus | 0.74 | ✓ | 0.06s |
| C07 | Simple factual question (what is + light signal) | haiku | haiku | 0.23 | ✓ | 0.07s |
| C08 | API documentation review (review signal, no length penalty) | sonnet | sonnet | 0.62 | ✓ | 0.06s |
| C09 | Refactor and restructure (two heavy signals) | opus | opus | 0.74 | ✓ | 0.06s |
| C10 | Debug, investigate, root cause (three heavy signals) | opus | opus | 0.86 | ✓ | 0.06s |

## Single Session

> Runs the job as a single Claude session.

| ID | Test | | architekton | plain | Speedup |
|----|------|-|-------------|-------|---------|
| S01 | List and describe files | ✓ | 65.6s | 29.2s | 0.4× |
| S02 | Code review of small project | ✓ | 252.5s | 72.9s | 0.3× |
| S03 | Design extension for small project | ✗ | 412.0s | 36.2s | 0.1× |

### S01 — session output

```
============================================================

[plain] exit=0 elapsed=29.2s
```


### S02 — session output

```
============================================================

[plain] exit=0 elapsed=72.9s
```


### S03 — session output

```
============================================================

[plain] exit=0 elapsed=36.2s
```


## Parallel Jobs

> The main feature.

| ID | Test | | architekton | plain | Speedup |
|----|------|-|-------------|-------|---------|
| P01 | Parallel file summaries (auto config) | ✓ | 209.7s | 32.3s | 0.2× |
| P02 | Parallel file summaries (2 workers, haiku) | ✓ | 254.7s | 42.2s | 0.2× |
| P03 | Parallel file summaries (sonnet workers) | ✓ | 159.6s | 61.3s | 0.4× |
| P04 | Parallel file summaries (opus orchestrator, haiku workers) | ✓ | 155.2s | 76.4s | 0.5× |
| P05 | Parallel code review (quality-sensitive task) | ✓ | 329.6s | 73.4s | 0.2× |

### P01 — session output

```
============================================================

[plain] exit=0 elapsed=32.3s
```


### P02 — session output

```
============================================================

[plain] exit=0 elapsed=42.2s
```


### P03 — session output

```
============================================================

[plain] exit=0 elapsed=61.3s
```


### P04 — session output

```
============================================================

[plain] exit=0 elapsed=76.4s
```


### P05 — session output

```
============================================================

[plain] exit=0 elapsed=73.4s
```


## Thinking Levels

> Runs the same parallel job four times with different thinking effort levels (low, med, high, ext).

| ID | Test | | architekton | plain | Speedup |
|----|------|-|-------------|-------|---------|
| T01 | Thinking=low (haiku baseline) | ✓ | 186.9s | 25.8s | 0.1× |
| T02 | Thinking=med (sonnet default) | ✓ | 184.4s | 32.0s | 0.2× |
| T03 | Thinking=high (opus default) | ✓ | 169.1s | 98.5s | 0.6× |
| T04 | Thinking=ext (maximum effort) | ✓ | 162.1s | 28.5s | 0.2× |

### T01 — session output

```
============================================================

[plain] exit=0 elapsed=25.8s
```


### T02 — session output

```
============================================================

[plain] exit=0 elapsed=32.0s
```


### T03 — session output

```
============================================================

[plain] exit=0 elapsed=98.5s
```


### T04 — session output

```
============================================================

[plain] exit=0 elapsed=28.5s
```


## Cost Comparison

> Head-to-head: architekton auto config vs plain claude on tasks of different sizes.

| ID | Test | | architekton | plain | Speedup |
|----|------|-|-------------|-------|---------|
| X01 | Small task: with vs without architekton | ✓ | 157.5s | 40.7s | 0.3× |
| X02 | Medium task: with vs without architekton | ✓ | 180.0s | 71.7s | 0.4× |
| X03 | Large parallel task: with vs without architekton | ✓ | 234.9s | 35.0s | 0.1× |

### X01 — session output

```
============================================================

[plain] exit=0 elapsed=40.7s
```


### X02 — session output

```
============================================================

[plain] exit=0 elapsed=71.7s
```


### X03 — session output

```
============================================================

[plain] exit=0 elapsed=35.0s
```


## Prose Generation

> Parallel prose tasks: documentation, explanations, and summaries.

| ID | Test | | architekton | plain | Speedup |
|----|------|-|-------------|-------|---------|
| G01 | Parallel docstrings (auto config) | ✓ | 233.8s | 31.7s | 0.1× |
| G02 | Parallel plain-English module explanations | ✓ | 194.9s | 37.0s | 0.2× |
| G03 | Parallel architecture docs per module | ✓ | 250.1s | 29.4s | 0.1× |

### G01 — session output

```
============================================================

[plain] exit=0 elapsed=31.7s
```


### G02 — session output

```
============================================================

[plain] exit=0 elapsed=37.0s
```


### G03 — session output

```
============================================================

[plain] exit=0 elapsed=29.4s
```


## Math Computation

> Tasks requiring algorithmic reasoning: complexity analysis, test generation, and performance profiling.

| ID | Test | | architekton | plain | Speedup |
|----|------|-|-------------|-------|---------|
| M01 | Parallel Big-O complexity analysis | ✓ | 300.3s | 93.9s | 0.3× |
| M02 | Parallel unit test generation | ✓ | 261.7s | 33.8s | 0.1× |
| M03 | Parallel performance bottleneck analysis | ✓ | 352.4s | 129.0s | 0.4× |

### M01 — session output

```
============================================================

[plain] exit=0 elapsed=93.9s
```


### M02 — session output

```
============================================================

[plain] exit=0 elapsed=33.7s
```


### M03 — session output

```
============================================================

[plain] exit=0 elapsed=129.0s
```


## Filesystem Mapping

> Whole-codebase tasks that require reading every file and building a coherent model of the project.

| ID | Test | | architekton | plain | Speedup |
|----|------|-|-------------|-------|---------|
| F01 | Cross-module dependency map (whole-codebase task) | ✓ | 157.4s | 76.5s | 0.5× |
| F02 | Cross-file function call graph | ✓ | 418.1s | 70.2s | 0.2× |
| F03 | Dead code and unused symbol detection | ✓ | 291.0s | 88.7s | 0.3× |

### F01 — session output

```
============================================================

[plain] exit=0 elapsed=76.5s
```


### F02 — session output

```
============================================================

[plain] exit=0 elapsed=70.2s
```


### F03 — session output

```
============================================================

[plain] exit=0 elapsed=88.7s
```


---
*Generated by architekton benchmark runner*
