// AskBox — the Attio-style "Ask anything…" input for starting a run.
//
// A large rounded box: a task textarea on top, and a bottom row with the
// agent picker (like Attio's "Auto"), a slash button that opens starter
// task templates, a mic button for voice input (only when the browser
// supports it), and a teal send button. Submitting calls the real
// run-creation path (api.createRun) — this is the primary way to start a
// run, not a dead input.
import { ArrowUp, Mic, Slash } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import type { Agent } from '../lib/types';
import { markStepDone } from '../lib/gettingStarted';
import { cn } from '../lib/cn';

const TEMPLATES = [
  'Research vendor Acme Corp and draft a brief',
  'Update the CRM record for Globex Ltd with the latest contact',
  'Draft a brief on vendor Initech from the latest research',
];

type SpeechRecognitionCtor = new () => {
  lang: string;
  interimResults: boolean;
  onresult: ((e: { results: { transcript: string }[][] }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function speechCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function AskBox({
  initialTask = '',
  inputRef,
  onRunCreated,
}: {
  initialTask?: string;
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
  onRunCreated: (runId: string) => void;
}) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agent, setAgent] = useState('auto');
  const [task, setTask] = useState(initialTask);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const innerRef = useRef<HTMLTextAreaElement>(null);
  const recogRef = useRef<InstanceType<SpeechRecognitionCtor> | null>(null);
  const micSupported = speechCtor() !== null;

  const ref = inputRef ?? innerRef;

  useEffect(() => {
    let cancelled = false;
    api.agents().then((a) => !cancelled && setAgents(a)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  function focusInput() {
    ref.current?.focus();
  }

  function pickTemplate(t: string) {
    setTask(t);
    setMenuOpen(false);
    focusInput();
  }

  function toggleMic() {
    const Ctor = speechCtor();
    if (!Ctor) return;
    if (listening) {
      recogRef.current?.stop();
      return;
    }
    const recog = new Ctor();
    recog.lang = 'en-US';
    recog.interimResults = false;
    recog.onresult = (e) => {
      const text = Array.from(e.results).map((r) => r[0]?.transcript ?? '').join(' ').trim();
      if (text) setTask((prev) => (prev ? `${prev} ${text}` : text));
    };
    recog.onend = () => setListening(false);
    recogRef.current = recog;
    setListening(true);
    try {
      recog.start();
    } catch {
      setListening(false);
    }
  }

  async function submit() {
    const text = task.trim();
    if (!text || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const agentId = agent === 'auto' ? (agents[0]?.id ?? 'scout') : agent;
      const res = await api.createRun(agentId, text);
      markStepDone('run');
      setTask('');
      onRunCreated(res.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the run');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div
        className={cn(
          'rounded-xl border border-border bg-white transition-colors',
          'focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/10',
        )}
      >
        <textarea
          ref={ref}
          value={task}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={3}
          placeholder="Ask anything…"
          aria-label="Ask an agent to do something"
          className="w-full resize-none bg-transparent px-4 pt-4 text-[15px] leading-relaxed text-ink placeholder:text-muted focus:outline-none"
        />
        <div className="flex items-center justify-end gap-1 px-3 pb-3 pt-1">
          <label className="sr-only" htmlFor="ask-agent">Agent</label>
          <select
            id="ask-agent"
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
            className="cursor-pointer appearance-none rounded-md bg-transparent px-2 py-1.5 text-sm text-muted hover:bg-wash hover:text-ink focus:outline-none"
          >
            <option value="auto">Auto</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Starter tasks"
              title="Starter tasks"
              className="rounded-md p-1.5 text-muted hover:bg-wash hover:text-ink"
            >
              <Slash className="h-4 w-4" strokeWidth={1.5} />
            </button>
            {menuOpen && (
              <>
                <button
                  type="button"
                  aria-label="Close starter tasks"
                  className="fixed inset-0 z-10 cursor-default"
                  onClick={() => setMenuOpen(false)}
                />
                <div className="absolute bottom-10 right-0 z-20 w-80 rounded-lg border border-border bg-white py-1 shadow-md">
                  <p className="px-3 pb-1 pt-2 text-xs font-medium text-faint">Starter tasks</p>
                  {TEMPLATES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => pickTemplate(t)}
                      className="block w-full px-3 py-2 text-left text-[13px] leading-snug text-body hover:bg-wash hover:text-ink"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          {micSupported && (
            <button
              type="button"
              onClick={toggleMic}
              aria-label={listening ? 'Stop listening' : 'Dictate a task'}
              title={listening ? 'Stop listening' : 'Dictate a task'}
              className={cn(
                'rounded-md p-1.5 hover:bg-wash hover:text-ink',
                listening ? 'bg-tint-error text-error' : 'text-muted',
              )}
            >
              <Mic className="h-4 w-4" strokeWidth={1.5} />
            </button>
          )}
          <button
            type="button"
            onClick={submit}
            disabled={!task.trim() || submitting}
            aria-label="Start run"
            title="Start run"
            className="ml-1 flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white transition-colors hover:bg-accent-dark disabled:cursor-not-allowed disabled:bg-tint-neutral disabled:text-faint"
          >
            <ArrowUp className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-error">{error}</p>}
    </div>
  );
}
