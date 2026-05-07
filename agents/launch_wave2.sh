#!/bin/bash
# Pixiis Wave 2 multi-agent launcher.
# Creates a tmux session `pixiis-wave2` with ONE window split into a 3x3 tile
# of 9 panes, each running an interactive `claude` CLI loaded with its brief.
# Mouse mode on — click any pane to focus it.
#
# After this script finishes, run:    !tmux attach -t pixiis-wave2
#
# Inside:  click any pane to focus  |  Ctrl-b z  zoom toggle  |  Ctrl-b d  detach

set -euo pipefail

SESSION=pixiis-wave2
WT=/mnt/d/code/python/pixiis/.worktrees

# pane_dir : brief_filename : branch_name
declare -a PANES=(
  "wave2-chrome:wave2-pane0-chrome.md:wave2/chrome-fix"
  "wave2-voice:wave2-pane1-voice.md:wave2/voice"
  "wave2-tts:wave2-pane2-tts.md:wave2/tts"
  "wave2-scanners-misc:wave2-pane3-scanners.md:wave2/scanners-misc"
  "wave2-xbox:wave2-pane4-xbox.md:wave2/xbox"
  "wave2-settings:wave2-pane5-settings.md:wave2/settings-page"
  "wave2-onboarding:wave2-pane6-onboarding.md:wave2/onboarding-page"
  "wave2-files:wave2-pane7-files.md:wave2/files-page"
  "wave2-library-polish:wave2-pane8-library-polish.md:wave2/library-polish"
)

# Tear down any stale session.
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create session with the first pane.
FIRST=${PANES[0]}
DIR0=${FIRST%%:*}
tmux new-session -d -s "$SESSION" -x 280 -y 72 -c "$WT/$DIR0" -n build

# Mouse: click pane to focus, scroll wheel, drag borders to resize.
tmux set-option -t "$SESSION" -g mouse on

# Pane border with index + title so the user can identify each pane.
tmux set-option -t "$SESSION" pane-border-status top
tmux set-option -t "$SESSION" pane-border-format ' #{pane_index}: #{pane_title} '

# Title pane 0.
tmux select-pane -t "$SESSION:0.0" -T "$DIR0"

# Add 8 more panes, **re-tiling after each split** so we never run out of space.
for i in 1 2 3 4 5 6 7 8; do
  P=${PANES[$i]}
  DIR=${P%%:*}
  tmux split-window -t "$SESSION" -c "$WT/$DIR"
  tmux select-pane -T "$DIR"
  tmux select-layout -t "$SESSION" tiled
done

# Final tile to make sure layout is even.
tmux select-layout -t "$SESSION" tiled

# Status line.
tmux set-option -t "$SESSION" -g status on
tmux set-option -t "$SESSION" -g status-left "#[bold] Pixiis Wave 2 #[default]"
tmux set-option -t "$SESSION" -g status-left-length 24
tmux set-option -t "$SESSION" -g window-status-format " #I:#W "
tmux set-option -t "$SESSION" -g window-status-current-format "#[reverse] #I:#W #[default]"

# Launch claude in each pane with its brief loaded.
for i in 0 1 2 3 4 5 6 7 8; do
  P=${PANES[$i]}
  IFS=':' read -r DIR BRIEF BRANCH <<< "$P"

  PROMPT="You are an agent in the Pixiis Wave 2 multi-agent build. Your worktree is the current working directory and you are on git branch $BRANCH. First read /mnt/d/code/python/pixiis/agents/CONTEXT_WAVE2.md (shared context — different from Wave 1's CONTEXT.md). Then read your brief at /mnt/d/code/python/pixiis/agents/$BRIEF and execute it. Update /mnt/d/code/python/pixiis/agents/STATUS.md as you progress per the brief's Reporting section. Do not edit other panes' worktrees. The user is attached to your tmux pane and can chat with you directly."

  tmux send-keys -t "$SESSION:0.$i" "claude \"$PROMPT\"" Enter
done

cat <<EOF

================================================================
  Pixiis Wave 2 launched — session: $SESSION
================================================================

  >>> ATTACH NOW by pasting this in your terminal: <<<
  !tmux attach -t $SESSION

  Inside the session:
    Click any pane         — focus it (mouse on)
    Ctrl-b z               — zoom focused pane to fullscreen
    Ctrl-b ←/↑/↓/→         — move directionally
    Ctrl-b d               — detach (session keeps running)

  9 panes (3x3 tile):
    0 chrome           Window drag fix + button polish
    1 voice            whisper-rs lift to src-tauri/src/voice/
    2 tts              Kokoro lift to src-tauri/src/voice/tts.rs
    3 scanners-misc    Epic / GOG / EA / StartMenu providers
    4 xbox             UWP scanner lift (uwp-detect spike → library/xbox.rs)
    5 settings-page    Editorial Settings (sectioned form + voice test)
    6 onboarding-page  Editorial Onboarding (5 steps with cross-fades)
    7 files-page       Manual entries editor
    8 library-polish   Review + tighten Library / GameDetail

  Status board: /mnt/d/code/python/pixiis/agents/STATUS.md
================================================================
EOF
