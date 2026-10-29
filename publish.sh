#!/bin/bash
# 把 site/（gh-pages worktree）以單一 commit 強推，不累積歷史，repo 不會越來越大
set -euo pipefail
cd site
touch .nojekyll
git config user.name "good-morning-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout -q --orphan "publish-$RANDOM"
git add -A
git commit -qm "$1 ($(TZ=Asia/Taipei date '+%Y-%m-%d %H:%M'))"
git push -qf origin HEAD:gh-pages
