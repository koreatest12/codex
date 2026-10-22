#!/usr/bin/env bash
# Local-only helper. Never commit, echo, download, or print actual Datadog keys.
set -euo pipefail

repository="koreatest12/codex"
artifact="datadog-synthetics-summary"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/datadog-synthetics.sh install
  bash scripts/datadog-synthetics.sh status
  bash scripts/datadog-synthetics.sh run [test-search-query] [datadog-site]
  bash scripts/datadog-synthetics.sh download RUN_ID [directory]

Prerequisite: install GitHub CLI, then run 'gh auth login'.
Install reads your Datadog keys from a hidden local terminal prompt and securely
uploads them to GitHub Actions secrets (DD_API_KEY and DD_APP_KEY).
Download retrieves ONLY a non-secret test result summary. It cannot export keys.
HELP
}

if [[ $# -eq 0 || "${1}" == "-h" || "${1}" == "--help" ]]; then
  usage
  exit 0
fi

command -v gh >/dev/null 2>&1 || {
  echo "GitHub CLI (gh) is required: https://cli.github.com/" >&2
  exit 69
}
gh auth status >/dev/null || {
  echo "GitHub authentication is required: gh auth login" >&2
  exit 69
}

command_name="$1"
shift
case "$command_name" in
  install)
    if [[ $# -ne 0 ]]; then usage >&2; exit 64; fi
    if [[ ! -r /dev/tty ]]; then
      echo "Run install from an interactive local terminal, not CI." >&2
      exit 69
    fi
    for secret_name in DD_API_KEY DD_APP_KEY; do
      printf 'Enter %s (hidden input): ' "$secret_name" > /dev/tty
      secret_value=''
      if ! IFS= read -r -s secret_value < /dev/tty; then
        printf '\n' > /dev/tty
        echo "Could not read secret from terminal." >&2
        exit 69
      fi
      printf '\n' > /dev/tty
      if [[ -z "$secret_value" ]]; then
        echo "Empty secret is not allowed; nothing was uploaded for $secret_name." >&2
        exit 64
      fi
      printf '%s' "$secret_value" | gh secret set "$secret_name" --app actions --repo "$repository"
      unset secret_value
      echo "$secret_name uploaded to GitHub Actions Secrets (value hidden)."
    done
    ;;
  status)
    if [[ $# -ne 0 ]]; then usage >&2; exit 64; fi
    names="$(gh secret list --app actions --repo "$repository" --json name --jq '.[].name')"
    for secret_name in DD_API_KEY DD_APP_KEY; do
      if grep -Fxq "$secret_name" <<< "$names"; then
        echo "$secret_name: configured (value inaccessible)"
      else
        echo "$secret_name: not configured"
      fi
    done
    ;;
  run)
    if [[ $# -gt 2 ]]; then usage >&2; exit 64; fi
    query="${1:-tag:e2e-tests}"
    site="${2:-datadoghq.com}"
    [[ -n "$query" && "$site" =~ ^[a-zA-Z0-9.-]+$ ]] || {
      echo "Query or Datadog site is invalid." >&2
      exit 64
    }
    gh workflow run datadog-synthetics.yml --repo "$repository" --ref main \
      -f "test_search_query=$query" -f "datadog_site=$site"
    echo "Manual run requested. View status: gh run list --repo $repository --workflow datadog-synthetics.yml"
    ;;
  download)
    if [[ $# -lt 1 || $# -gt 2 || ! "$1" =~ ^[0-9]+$ ]]; then
      echo "Provide a numeric workflow RUN_ID and optional destination directory." >&2
      usage >&2
      exit 64
    fi
    run_id="$1"
    destination="${2:-.ci-reports/datadog-${run_id}}"
    mkdir -p -- "$destination"
    gh run download "$run_id" --repo "$repository" --name "$artifact" --dir "$destination"
    echo "Sanitized summary downloaded to: $destination"
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac
