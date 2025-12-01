# Jira Transitions Cheat Sheet

This notes how to move Jira issues into the target statuses via the REST API (“In Development”, “In Review”, “Awaiting QA”), even when workflows differ.

## Transition APIs
- List transitions: `GET /rest/api/3/issue/{issueKey}/transitions?expand=transitions.fields`
- Perform transition: `POST /rest/api/3/issue/{issueKey}/transitions`
  ```json
  { "transition": { "id": "<transitionId>" }, "fields": { /* only if required */ } }
  ```
- Auth: Basic (email + API token)
- Transition IDs and names are per-project/workflow; fetch per issue.

## Finding a transition to a target status
1) Call `GET transitions`.
2) Prefer a transition whose `to.name` matches your target (case-insensitive).
3) If none, try matching `transition.name` to your target.
4) If still none, you need a multi-step path (BFS over statuses):
   - For each reachable status, fetch its transitions, repeat until `to.name` is the target.
   - Otherwise report “no transition to target” so you can adjust target names.

## Required fields
If a transition requires fields, they appear under `transitions.fields` when using `expand=transitions.fields`. Include them in the POST; otherwise leave `fields` empty.

## Targets to reach
- In Development: target names e.g. `["In Development"]` (tweak per workflow)
- In Review: `["In Review"]`
- Awaiting QA: e.g. `["Awaiting QA", "Ready for QA", "QA"]`

## Execution flow (per issue)
1) `GET /issue/{key}/transitions?expand=transitions.fields`
2) Find transition where `to.name` is in the target list; POST it.
3) Else, find transition where `transition.name` matches target; POST it.
4) Else, BFS through reachable statuses until a transition to target is found; execute that path (requires extra logic).
5) If none found, log available transitions; do not guess.

## Safety
- Keep this feature behind a flag/UI button; avoid automatic transitions.
- Ensure the API user has transition permissions for the project.
- If 403 or required fields are missing, surface that to the user.

This gives you a roadmap to drive issues into “In Development”, “In Review”, or “Awaiting QA” via Jira’s API, even with varied workflows. Keep target status lists configurable per project. 
