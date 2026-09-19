# Edge Functions, not built yet

- `trigger-apply`: verifies the caller is the owner (JWT email), sets status `queued`, and calls GitHub
  `POST /repos/{owner}/{repo}/dispatches` with a fine-grained PAT stored as a function secret.
