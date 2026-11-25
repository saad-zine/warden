// Getting-started progress for the sidebar pill (Attio-style "Getting started n/6").
//
// Steps are real: most are derived from the backend (so history from earlier
// sessions counts), and every step is also recorded in localStorage when the
// action happens in this browser — the backend has no "list all approvals"
// endpoint, so a decided approval is only visible via the local flag.
// The "live backend" step is computed from the current mode.
import { api } from './api';

export type StepId = 'run' | 'approval' | 'memory' | 'eval' | 'quest' | 'live';

export const STEPS: { id: StepId; label: string }[] = [
  { id: 'run', label: 'Run your first agent run' },
  { id: 'approval', label: 'Review an approval' },
  { id: 'memory', label: 'Save a memory' },
  { id: 'eval', label: 'Run the eval suite' },
  { id: 'quest', label: 'Complete a quest' },
  { id: 'live', label: 'Connect the live backend' },
];

const KEY = 'warden:getting-started';
const EVENT = 'warden:progress';

function readFlags(): Partial<Record<StepId, true>> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Record<StepId, true>>;
  } catch {
    return {};
  }
}

/** Record that the user just did this step (in this browser). */
export function markStepDone(id: StepId) {
  try {
    const flags = readFlags();
    flags[id] = true;
    localStorage.setItem(KEY, JSON.stringify(flags));
  } catch {
    // localStorage unavailable — progress just won't persist.
  }
  window.dispatchEvent(new Event(EVENT));
}

/** Subscribe to progress changes (marks made elsewhere in the app). */
export function subscribeProgress(fn: () => void): () => void {
  window.addEventListener(EVENT, fn);
  return () => window.removeEventListener(EVENT, fn);
}

export async function loadProgress(mode: string): Promise<{ done: number; total: number }> {
  const flags = readFlags();
  const [stats, memory, evals, quests] = await Promise.allSettled([
    api.stats(),
    api.memory(),
    api.evals(),
    api.quests(),
  ]);
  const done = new Set<StepId>();
  if (flags.run || (stats.status === 'fulfilled' && stats.value.runs_total > 0)) done.add('run');
  if (flags.approval) done.add('approval');
  if (flags.memory || (memory.status === 'fulfilled' && memory.value.length > 0)) done.add('memory');
  if (flags.eval || (evals.status === 'fulfilled' && evals.value.length > 0)) done.add('eval');
  if (flags.quest || (quests.status === 'fulfilled' && quests.value.some((q) => q.status === 'done'))) done.add('quest');
  if (mode === 'live') done.add('live');
  return { done: done.size, total: STEPS.length };
}
