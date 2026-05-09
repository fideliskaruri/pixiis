/**
 * ActionFooter — Persistent Steam Big Picture / Xbox-style controller
 * hint bar at the bottom of the viewport.
 *
 * Reads from <ActionFooterProvider>. Each page and modal registers its
 * relevant button → verb mappings via useActionFooter(); this component
 * just renders whatever is currently in the provider state, with a
 * sensible default fallback when nothing is registered (rare — only
 * during route transitions).
 *
 * Layout:
 *   - position: fixed, bottom of viewport, full width
 *   - height: 56px in TV mode (body.is-fullscreen), 40px windowed
 *   - background: --bg at 92% over a 1px --rule top hairline
 *   - actions are space-separated by a centred dot (·) at 50% opacity
 *   - glyphs are coloured per Xbox conventions:
 *       A green / B red / X blue / Y yellow
 *     LB/RB/LT/RT/START/SELECT are wider rounded-rect chips with a
 *     neutral surface so they read as "shoulder buttons", not face
 *     buttons.
 */

import { useActionFooterState, type FooterAction, type FooterGlyph } from '../api/ActionFooterContext';
import './ActionFooter.css';

const DEFAULT_ACTIONS: FooterAction[] = [
  { glyph: 'A', verb: 'Select' },
  { glyph: 'B', verb: 'Back' },
  { glyph: 'LB', verb: 'Tab' },
  { glyph: 'RB', verb: 'Tab' },
  { glyph: 'Y', verb: 'Search' },
];

const FACE_BUTTONS: FooterGlyph[] = ['A', 'B', 'X', 'Y'];

function glyphClass(glyph: FooterGlyph): string {
  if (FACE_BUTTONS.includes(glyph)) {
    return `actfoot__glyph actfoot__glyph--face actfoot__glyph--${glyph.toLowerCase()}`;
  }
  return `actfoot__glyph actfoot__glyph--shoulder actfoot__glyph--${glyph.toLowerCase()}`;
}

function glyphLabel(glyph: FooterGlyph): string {
  // START and SELECT look better at a single-letter scale on the chip.
  // We expose them as their full label here (the chip is wide enough),
  // and let the CSS shrink the type if needed.
  return glyph;
}

export function ActionFooter() {
  const { actions } = useActionFooterState();
  const list = actions.length > 0 ? actions : DEFAULT_ACTIONS;

  // Fall through invisibly if a caller explicitly clears the bar — but
  // keep DOM presence so the hairline doesn't pop in/out when modals
  // race the page register.
  return (
    <div className="actfoot" role="contentinfo" aria-label="Controller actions">
      <div className="actfoot__inner">
        {list.map((action, i) => (
          <span
            className="actfoot__action"
            key={`${action.glyph}:${action.verb}:${i}`}
          >
            <span className={glyphClass(action.glyph)} aria-hidden="true">
              {glyphLabel(action.glyph)}
            </span>
            <span className="actfoot__verb">{action.verb}</span>
            {action.context !== undefined && action.context !== '' && (
              <span className="actfoot__context"> · {action.context}</span>
            )}
            {i < list.length - 1 && (
              <span className="actfoot__sep" aria-hidden="true">
                ·
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
