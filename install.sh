#!/bin/sh
# Installs the pirlo command on Linux, WSL or macOS, then runs `pirlo setup`, which asks
# in the terminal which AIs to use, the scope and the worker. Run it again to update.
# Optional settings:
#   PIRLO_BIN_DIR     where the command goes (default: ~/.local/bin)
#   PIRLO_SKILLS_DIR  also install the skills there, for CLIs that read Agent Skills
#   PIRLO_NO_SETUP    set to skip the setup questions
set -eu

repo="https://raw.githubusercontent.com/isaiasaltoe/pirlo/main"
bin_dir="${PIRLO_BIN_DIR:-$HOME/.local/bin}"
here=$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")

command -v python3 >/dev/null 2>&1 || { echo "pirlo needs python3 (3.9 or newer)" >&2; exit 1; }

# Copy from this clone when run from one, else download (curl ... | sh).
fetch() {
  if [ -n "$here" ] && [ -f "$here/install.sh" ] && [ -f "$here/$1" ]; then
    cp "$here/$1" "$2"
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL "$repo/$1" -o "$2"
  else
    wget -qO "$2" "$repo/$1"
  fi
}

mkdir -p "$bin_dir"
tmp="$bin_dir/.pirlo.$$"
fetch bin/pirlo "$tmp"
chmod +x "$tmp"
mv "$tmp" "$bin_dir/pirlo"
echo "installed $("$bin_dir/pirlo" --version) in $bin_dir/pirlo"

if [ -n "${PIRLO_SKILLS_DIR:-}" ]; then
  for skill in pirlo pirlo-setup pirlo-savings; do
    mkdir -p "$PIRLO_SKILLS_DIR/$skill"
    fetch "portable/skills/$skill/SKILL.md" "$PIRLO_SKILLS_DIR/$skill/SKILL.md"
  done
  echo "installed the skills in $PIRLO_SKILLS_DIR"
fi

# With curl | sh, stdin is this script, so the questions read from the terminal itself.
if [ -z "${PIRLO_NO_SETUP:-}" ] && { : </dev/tty; } 2>/dev/null; then
  echo
  "$bin_dir/pirlo" setup </dev/tty || true
else
  echo "next: run 'pirlo setup' in a terminal"
fi

case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "add $bin_dir to your PATH, for example: echo 'export PATH=\"$bin_dir:\$PATH\"' >> ~/.profile" ;;
esac
