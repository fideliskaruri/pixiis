/**
 * useController — Xbox controller input via the Gamepad API.
 *
 * Polls connected gamepads at 60Hz and provides:
 * - Button press events (rising edge only)
 * - D-pad / stick direction
 * - Trigger values
 *
 * Works in Tauri's webview (Chromium-based).
 */

import { useEffect, useRef, useCallback } from 'react';

export type ControllerButton =
  | 'a' | 'b' | 'x' | 'y'
  | 'lb' | 'rb'
  | 'lt' | 'rt'
  | 'start' | 'select'
  | 'ls' | 'rs'
  | 'up' | 'down' | 'left' | 'right';

export type Direction = 'up' | 'down' | 'left' | 'right' | null;

// Standard Gamepad button mapping (Xbox layout)
const BUTTON_MAP: [number, ControllerButton][] = [
  [0, 'a'], [1, 'b'], [2, 'x'], [3, 'y'],
  [4, 'lb'], [5, 'rb'],
  [6, 'lt'], [7, 'rt'],
  [8, 'select'], [9, 'start'],
  [10, 'ls'], [11, 'rs'],
  [12, 'up'], [13, 'down'], [14, 'left'], [15, 'right'],
];

const DEADZONE = 0.3;

type ButtonHandler = (button: ControllerButton) => void;
type DirectionHandler = (dir: Direction) => void;

export function useController(
  onButtonPress?: ButtonHandler,
  onDirection?: DirectionHandler,
) {
  const prevState = useRef<Record<ControllerButton, boolean>>({} as any);
  const prevDir = useRef<Direction>(null);
  const animFrame = useRef<number>(0);

  const poll = useCallback(() => {
    const gamepads = navigator.getGamepads();
    const gp = gamepads[0]; // First connected gamepad

    if (!gp) {
      animFrame.current = requestAnimationFrame(poll);
      return;
    }

    // ── Button edge detection ───────────────────────────────────
    for (const [idx, name] of BUTTON_MAP) {
      const pressed = gp.buttons[idx]?.pressed ?? false;
      const was = prevState.current[name] ?? false;

      if (pressed && !was && onButtonPress) {
        onButtonPress(name);
      }
      prevState.current[name] = pressed;
    }

    // ── Direction from D-pad + left stick ────────────────────────
    let dir: Direction = null;

    // D-pad takes priority (buttons 12-15)
    if (gp.buttons[12]?.pressed) dir = 'up';
    else if (gp.buttons[13]?.pressed) dir = 'down';
    else if (gp.buttons[14]?.pressed) dir = 'left';
    else if (gp.buttons[15]?.pressed) dir = 'right';

    // Left stick fallback
    if (!dir) {
      const lx = gp.axes[0] ?? 0;
      const ly = gp.axes[1] ?? 0;
      if (Math.abs(lx) > DEADZONE || Math.abs(ly) > DEADZONE) {
        if (Math.abs(lx) > Math.abs(ly)) {
          dir = lx < 0 ? 'left' : 'right';
        } else {
          dir = ly < 0 ? 'up' : 'down';
        }
      }
    }

    if (dir !== prevDir.current && onDirection) {
      onDirection(dir);
    }
    prevDir.current = dir;

    animFrame.current = requestAnimationFrame(poll);
  }, [onButtonPress, onDirection]);

  useEffect(() => {
    animFrame.current = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(animFrame.current);
  }, [poll]);
}

/**
 * Get the current state of the right trigger (0.0 to 1.0).
 * Useful for voice recording threshold detection.
 */
export function getRightTrigger(): number {
  const gp = navigator.getGamepads()[0];
  if (!gp) return 0;
  return gp.buttons[7]?.value ?? 0;
}
