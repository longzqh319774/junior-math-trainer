#!/usr/bin/env bash
# One-shot: create remote, push to GitHub.
# Edit USERNAME below before first use.
set -e

USERNAME="longzqh319774"
REPO="junior-math-trainer"

cd "$(dirname "$0")"

echo "==> Target: https://github.com/$USERNAME/$REPO.git"
echo "==> Make sure this empty repo exists on GitHub first."

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$USERNAME/$REPO.git"
git branch -M main
git push -u origin main

cat <<EOF

==> Pushed.
Next: GitHub repo -> Settings -> Pages -> Source: "GitHub Actions"
      Then every push to main auto-deploys the site/ folder.

NOTE: site/data.js and site/img/ are git-ignored, so your own
      question bank will NOT be uploaded.
EOF
