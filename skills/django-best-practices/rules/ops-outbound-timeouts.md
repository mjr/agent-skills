---
title: Give every outbound HTTP call a timeout
impact: HIGH
risk: availability
django: ">=5.2"
database: any
tags: timeout, http, requests, httpx, urllib, workers
sources:
  - https://hakibenita.com/9-django-tips-for-working-with-databases
tests: test_ops.py
---

## Give every outbound HTTP call a timeout

Python sockets have no default timeout, and neither `urllib` nor the `requests` library
sets one. A partner API that accepts the connection and never answers keeps the calling
worker blocked forever. A handful of such calls occupy every gunicorn worker, and the
whole application stops serving, although nothing in it is slow.

**Incorrect (waits as long as the remote side wants):**

```python
response = requests.post(PROVIDER_URL, json=payload)
```

**Correct (bounded connect and read time):**

```python
response = requests.post(PROVIDER_URL, json=payload, timeout=(3.05, 10))
```

The tuple sets the connect and read timeouts separately; a single number applies to each
phase. `httpx` has a default timeout of 5 seconds, but set it explicitly so the value is
a decision. Wrap provider SDKs whose calls do not take a timeout, or configure the
client they use.

Pick values shorter than the request timeout of the server (gunicorn's `--timeout`) and
than the transaction (see `tx-keep-short`), and move calls that need long waits into
background tasks.

**When not to apply:** nothing; even internal services fail by hanging.

**How to detect:** calls to `requests.`, `urlopen(`, `httpx.` and SDK clients without a
`timeout` argument; workers killed by the server's timeout with stack traces inside
socket reads.

Reference: [9 Django Tips for Working with Databases](https://hakibenita.com/9-django-tips-for-working-with-databases)
