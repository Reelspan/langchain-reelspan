# Changelog

## 0.1.0

First release.

- 12 tools: list profiles; publish video, photos and text (now, scheduled or queued, with first comment and network
  settings); post status, retry, history; scheduled posts and cancelling; profile analytics, post analytics, best times.
- `ReelspanToolkit` with one client: `profile` pins every tool to one profile, `platforms` limits the networks,
  `read_only` keeps only the tools that read, `wait` waits for each network's result.
- Errors go back to the model as tool messages it can act on; answers are trimmed to save tokens.
- Passes LangChain's standard tool tests.
