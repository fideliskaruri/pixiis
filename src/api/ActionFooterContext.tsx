/**
 * ActionFooterContext — Steam Big Picture-style controller hint registry.
 *
 * Pages and modals declare what each gamepad button does in the current
 * context by calling `useActionFooter([...])` on mount. The persistent
 * <ActionFooter> at the app root renders whichever set is currently
 * registered. On unmount, the entries clear and the footer falls back
 * to defaults (or to whatever underlying surface re-registers next).
 *
 * Modal override semantics:
 *   When a modal mounts and registers its own actions, it replaces the
 *   underlying page's set for the duration of its lifetime. When the
 *   modal unmounts, the page's effect re-runs (well — its dependencies
 *   haven't changed, but the page's most recent registration is the
 *   last one to "win" before the modal stomped it). To avoid relying on
 *   that subtlety, the page also re-registers on each render of its
 *   actions array (deps tracked via JSON.stringify) — when the modal
 *   clears, the next render of the page restores the page's set.
 *
 * The contract is intentionally one-deep: stack depth is implicit
 * via React's mount order. The most recently mounted caller wins; on
 * unmount, the previous caller's registration is whatever it last
 * pushed. We don't try to maintain a stack — modals are short-lived
 * and the page's hook re-fires whenever its inputs do.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type FooterGlyph =
  | 'A'
  | 'B'
  | 'X'
  | 'Y'
  | 'LB'
  | 'RB'
  | 'LT'
  | 'RT'
  | 'START'
  | 'SELECT';

export interface FooterAction {
  glyph: FooterGlyph;
  verb: string;
  context?: string;
  onActivate?: () => void;
}

interface ActionFooterApi {
  actions: FooterAction[];
  setActions: (a: FooterAction[]) => void;
}

const NOOP_API: ActionFooterApi = {
  actions: [],
  setActions: () => {
    /* no-op when called outside provider */
  },
};

const ActionFooterContext = createContext<ActionFooterApi>(NOOP_API);

export function ActionFooterProvider({ children }: { children: ReactNode }) {
  const [actions, setActions] = useState<FooterAction[]>([]);

  const value = useMemo<ActionFooterApi>(
    () => ({ actions, setActions }),
    [actions],
  );

  return (
    <ActionFooterContext.Provider value={value}>
      {children}
    </ActionFooterContext.Provider>
  );
}

export function useActionFooterState(): ActionFooterApi {
  return useContext(ActionFooterContext);
}

/**
 * Register footer actions for the lifetime of the calling component.
 *
 * On mount (and whenever the action set's visible content changes),
 * the new set is pushed. On unmount, the set is cleared — the
 * footer's fallback defaults apply until another component registers.
 *
 * Equality is content-based (JSON.stringify) so a fresh array literal
 * each render doesn't thrash the provider state.
 */
export function useActionFooter(actions: FooterAction[]): void {
  const ctx = useContext(ActionFooterContext);
  const setActions = ctx.setActions;
  // Memoise on the visible content. We strip onActivate from the key
  // because callbacks change identity per render and would otherwise
  // re-fire the effect every paint.
  const key = useMemo(
    () =>
      JSON.stringify(
        actions.map((a) => ({ glyph: a.glyph, verb: a.verb, context: a.context })),
      ),
    [actions],
  );
  // Snapshot the actions array under the same memo key — the effect
  // below uses this memoised value, never the live `actions` argument,
  // so the dep array stays in sync with what was actually pushed.
  const snapshot = useMemo(() => actions, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setActions(snapshot);
    return () => {
      setActions([]);
    };
  }, [snapshot, setActions]);
}

/**
 * Imperative version for callers that already manage their own array.
 * Useful when the action list depends on async state that isn't
 * straightforward to express through the hook deps.
 */
export function useActionFooterSetter(): (a: FooterAction[]) => void {
  const ctx = useContext(ActionFooterContext);
  return useCallback(
    (a: FooterAction[]) => ctx.setActions(a),
    [ctx],
  );
}
