import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
import { IVRPromptRecord } from "../types";

const PROMPT_KEYS = ["menu", "reprompt", "confirmation", "invalid"] as const;

const PROMPT_LABELS: Record<(typeof PROMPT_KEYS)[number], string> = {
  menu: "Menu Prompt",
  reprompt: "Reprompt (no input / unclear)",
  confirmation: "Confirmation (before connecting)",
  invalid: "Invalid selection message",
};

export function IVRPromptPanel() {
  const { data, isLoading, isError, error } = useQuery<IVRPromptRecord[]>({
    queryKey: ["ivr-prompts"],
    queryFn: api.listIVRPrompts,
  });
  const qc = useQueryClient();

  const [drafts, setDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data) return;
    const next: Record<string, string> = {};
    for (const key of PROMPT_KEYS) {
      const rec = data.find((p) => p.key === key);
      next[key] = rec?.message ?? "";
    }
    setDrafts(next);
  }, [data]);

  const upsertMutation = useMutation({
    mutationFn: async (payloads: { key: string; message: string }[]) => {
      await Promise.all(payloads.map((p) => api.upsertIVRPrompt(p.key, { message: p.message })));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ivr-prompts"] }),
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      await Promise.all(PROMPT_KEYS.map((key) => api.deleteIVRPrompt(key)));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ivr-prompts"] }),
  });

  const handleSave = () => {
    const payloads = PROMPT_KEYS.map((key) => ({ key, message: drafts[key]?.trim() ?? "" })).filter(
      (p) => p.message,
    );
    if (!payloads.length) return;
    upsertMutation.mutate(payloads);
  };

  const handleReset = () => {
    resetMutation.mutate();
  };

  if (isLoading) return <SectionShell title="IVR Prompts">Loading…</SectionShell>;
  if (isError) return <SectionShell title="IVR Prompts">Error: {(error as Error).message}</SectionShell>;

  return (
    <SectionShell
      title="IVR Prompts"
      subtitle="Control the English IVR messages for menu, reprompt, and confirmation"
    >
      <div className="space-y-6">
        {PROMPT_KEYS.map((key) => (
          <div key={key} className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-onyx">{PROMPT_LABELS[key]}</p>
            </div>
            <textarea
              value={drafts[key] ?? ""}
              onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
              rows={key === "menu" ? 4 : 3}
              className="w-full glass-panel rounded-3xl p-4 font-sans text-sm text-onyx/80 focus:outline-none focus:ring-2 focus:ring-garnet"
            />
          </div>
        ))}
        <div className="flex gap-3 justify-end">
          <button
            onClick={handleReset}
            disabled={resetMutation.isPending}
            className="px-4 py-2 rounded-full border border-sand-dark/60 text-sm text-onyx/70 hover:border-garnet disabled:opacity-50"
          >
            {resetMutation.isPending ? "Reverting…" : "Reset to Defaults"}
          </button>
          <button
            onClick={handleSave}
            disabled={upsertMutation.isPending}
            className="px-6 py-2 rounded-full bg-garnet text-white text-sm font-semibold hover:bg-garnet/90 disabled:opacity-50"
          >
            {upsertMutation.isPending ? "Saving…" : "Save IVR Prompts"}
          </button>
        </div>
      </div>
    </SectionShell>
  );
}

function SectionShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="glass-panel rounded-3xl p-8 space-y-4">
      <header className="flex flex-col gap-1">
        <p className="text-xs uppercase tracking-[0.4em] text-amber">{title}</p>
        {subtitle && <p className="text-onyx/70 text-sm">{subtitle}</p>}
      </header>
      {children}
    </section>
  );
}
