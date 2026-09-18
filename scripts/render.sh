#!/usr/bin/env bash
# Render the Open WebUI prompt artifacts from the canonical sources.
#
#   dist/system-prompt.md   Workspace Model "Cord": identity + tutor skill +
#                           learning science + this deployment's adaptations
#   dist/skills/<name>.md   one Open WebUI skill per learning-lab technique
#
# Sources are the two submodules and web/adaptations.md; dist/ is never
# hand-edited. scripts/seed.py pushes the outputs into a running instance.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
identity="$repo/cordell/identity/current.txt"
plugin="$repo/claude-plugins/plugins/learning-lab"
dist="$repo/dist"

[ -f "$identity" ] && [ -d "$plugin/skills" ] \
  || { echo "submodules missing; run: git submodule update --init" >&2; exit 1; }

# Phrases that assume the Claude Code harness. Anything this list can't cover
# is overridden in prose by web/adaptations.md.
adapt() {
  sed -E \
    -e 's#read `\$\{CLAUDE_PLUGIN_ROOT\}/references/learning-science\.md`#see the Learning science section of your system prompt#g' \
    -e 's#read `\$\{CLAUDE_PLUGIN_ROOT\}/references/persistence\.md`#see the Persistence section of your system prompt#g' \
    -e 's#`\$\{CLAUDE_PLUGIN_ROOT\}/references/learning-science\.md`#the Learning science section of your system prompt#g' \
    -e 's#`\$\{CLAUDE_PLUGIN_ROOT\}/references/persistence\.md`#the Persistence section of your system prompt#g' \
    -e 's#^`\$ARGUMENTS`#The learner'"'"'s message#' \
    -e 's#`\$ARGUMENTS`#the learner'"'"'s message#g' \
    -e 's#`date \+%F`#the date in your system prompt#g'
}

# Strip the YAML frontmatter block from a SKILL.md.
body() { awk 'NR==1 && /^---$/ {fm=1; next} fm && /^---$/ {fm=0; next} !fm' "$1"; }

# Emit frontmatter with only the keys Open WebUI skills use (name, description).
frontmatter() {
  awk '
    NR==1 && /^---$/ {fm=1; print; next}
    fm && /^---$/ {print; exit}
    fm && /^(name|description):/ {keep=1; print; next}
    fm && /^[A-Za-z0-9_-]+:/ {keep=0; next}
    fm && keep {print}
  ' "$1"
}

rm -rf "$dist/skills"
mkdir -p "$dist/skills"

{
  cat "$identity"
  echo
  body "$plugin/skills/tutor/SKILL.md" | adapt
  echo
  cat "$plugin/references/learning-science.md"
  echo
  cat "$repo/web/adaptations.md"
} > "$dist/system-prompt.md"

for dir in "$plugin"/skills/*/; do
  name="$(basename "$dir")"
  [ "$name" = tutor ] && continue
  { frontmatter "$dir/SKILL.md"; body "$dir/SKILL.md" | adapt; } \
    > "$dist/skills/$name.md"
done

ver="$(sed -nE 's/.*version="([^"]+)".*/\1/p' "$identity" | head -n1)"
echo "rendered dist/system-prompt.md ($(wc -w < "$dist/system-prompt.md") words, identity v$ver)"
ls "$dist/skills" | sed 's#^#rendered dist/skills/#'
