#!/usr/bin/env bash
# Put the hooks in this clone. Per-clone by design: `.git/hooks` is not shared, and the
# only clone that has a private half to check is the main checkout.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR="$(git -C "$ROOT" rev-parse --git-path hooks)"
mkdir -p "$DIR"
for hook in "$ROOT"/deploy/hooks/*; do
  name="$(basename "$hook")"
  [ "$name" = "install.sh" ] && continue
  install -m 755 "$hook" "$DIR/$name"
  echo "installed $name -> $DIR/$name"
done
