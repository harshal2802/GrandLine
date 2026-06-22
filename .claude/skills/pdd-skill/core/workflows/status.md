# Status

## Purpose

Provide a quick health check of the PDD setup and identify the most useful next action.

## Use When

- The user is unsure what is already set up.
- The repo may have stale or missing PDD artifacts.

## Inputs

- repository layout
- presence or freshness of context, prompts, and eval files

## Produces

- a concise health summary
- missing artifact warnings
- next-step guidance

## Default Next Step

Follow the highest-value missing step, usually `context`, `prompts`, or `review`.
