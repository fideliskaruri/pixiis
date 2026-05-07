#!/bin/bash
# Pixiis Wave 1 multi-agent launcher.
# Creates a tmux session `pixiis-build` with 9 windows (one per agent).
# Each window runs an interactive `claude` CLI loaded with a self-contained
# brief.
#
# Attach:        tmux attach -t pixiis-build
# Switch:        Ctrl-b + <0..8>   (window by number)
#                Ctrl-b + n / p    (next / prev)
#                Ctrl-b + w        (visual picker)
# Detach:        Ctrl-b + d
# Kill:          tmux kill-session -t pixiis-build

set -euo pipefail

SESSION=pixiis-build
WT=/mnt/d/code/python/pixiis/.worktrees

# pane_dir : brief_filename : branch_name
declare -a PANES=(
  "pane1-whisper:pane1-whisper.md:wave1/whisper-spike"
  "pane2-kokoro:pane2-kokoro.md:wave1/kokoro-spike"
  "pane3-uwp:pane3-uwp.md:wave1/uwp-spike"
  "pane4-baseline:pane4-baseline.md:wave1/baseline"
  "pane5-tauri:pane5-tauri.md:wave1/tauri-scaffold"
  "pane6-design:pane6-design.md:wave1/design-tokens"
  "pane7-types:pane7-types.md:wave1/types"
  "pane8-controller:pane8-controller.md:wave1/controller"
  "pane9-services:pane9-services.md:wave1/services"
)

# Tear down any stale session.
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create session with the first window (window 0).
FIRST=${PANES[0]}
DIR0=${FIRST%%:*}
tmux new-session -d -s "$SESSION" -c "$WT/$DIR0" -n "$DIR0"

# Add 8 more windows, each cd'd into its own worktree.
for i in 1 2 3 4 5 6 7 8; do
  P=${PANES[$i]}
  DIR=${P%%:*}
  tmux new-window -t "$SESSION" -c "$WT/$DIR" -n "$DIR"
done

# Make window numbering visible.
tmux set-option -t "$SESSION" -g status on
tmux set-option -t "$SESSION" -g status-left "#[bold] Pixiis-build #[default]"
tmux set-option -t "$SESSION" -g status-left-length 20
tmux set-option -t "$SESSION" -g window-status-format " #I:#W "
tmux set-option -t "$SESSION" -g window-status-current-format "#[reverse] #I:#W #[default]"

# Launch claude in each window with its brief loaded as the initial prompt.
for i in 0 1 2 3 4 5 6 7 8; do
  P=${PANES[$i]}
  IFS=':' read -r DIR BRIEF BRANCH <<< "$P"

  PROMPT="You are an agent in the Pixiis Wave 1 multi-agent build. Your worktree is the current working directory and you are on git branch $BRANCH. First read /mnt/d/code/python/pixiis/agents/CONTEXT.md (shared context). Then read your brief at /mnt/d/code/python/pixiis/agents/$BRIEF and execute it. Update /mnt/d/code/python/pixiis/agents/STATUS.md as you progress per the brief's Reporting section. Do not edit other panes' worktrees. The user is attached to your tmux window and can chat with you directly."

  tmux send-keys -t "$SESSION:$i" "claude \"$PROMPT\"" Enter
done

# Start on window 0.
tmux select-window -t "$SESSION:0"

cat <<EOF

================================================================
  Pixiis Wave 1 launched in tmux session: $SESSION
================================================================

  Attach:        tmux attach -t $SESSION
  Switch:        Ctrl-b + <number 0..8>     (jump to window)
                 Ctrl-b + w                 (visual picker)
                 Ctrl-b + n / p             (next / prev)
  Detach:        Ctrl-b + d
  Kill:          tmux kill-session -t $SESSION

  9 windows:
    0  pane1-whisper      whisper-rs spike
    1  pane2-kokoro       Kokoro ONNX spike
    2  pane3-uwp          UWP detect spike (no PowerShell)
    3  pane4-baseline     faster-whisper baseline + WAV fixture
    4  pane5-tauri        Tauri scaffold      (unblocks 6,7,8)
    5  pane6-design       Editorial design tokens
    6  pane7-types        types.rs            (waits on win 4)
    7  pane8-controller   gilrs controller    (waits on win 4)
    8  pane9-services     RAWG/Twitch/YT      (waits on win 4)

  Status board:  /mnt/d/code/python/pixiis/agents/STATUS.md

  Each agent will start by reading CONTEXT.md + its brief, then begin work.
  You can interrupt at any time and chat directly with the agent.
================================================================
EOF
