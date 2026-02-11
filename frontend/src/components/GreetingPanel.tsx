import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
import { GreetingRecord } from "../types";

const LANGUAGE_LABELS: Record<string, string> = {
  "en-IN": "English (India)",
  "hi-IN": "Hindi",
};

export function GreetingPanel() {
  const { data, isLoading, isError, error } = useQuery<GreetingRecord[]>({
    queryKey: ["greetings"],
    queryFn: api.listGreetings,
  });
  const [draft, setDraft] = useState("");
  const qc = useQueryClient();

  useEffect(() => {
    if (!data || data.length === 0) {
      setDraft("");
      return;
    }

    // Prefer English message then Hindi, otherwise empty
    const en = data.find((g) => g.language === "en-IN");
    const hi = data.find((g) => g.language === "hi-IN");
    setDraft(en?.message ?? hi?.message ?? "");
  }, [data]);

  const upsertMutation = useMutation({
    mutationFn: (message: string) => Promise.all([
      api.upsertGreeting("en-IN", { message }),
      api.upsertGreeting("hi-IN", { message }),
    ]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["greetings"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => Promise.all([
      api.deleteGreeting("en-IN"),
      api.deleteGreeting("hi-IN"),
    ]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["greetings"] }),
  });

  const handleSave = () => {
    const text = draft.trim();
    if (!text) return;
    upsertMutation.mutate(text);
  };

  const handleReset = () => {
    deleteMutation.mutate();
  };

  if (isLoading) return <SectionShell title="Default Greeting">Loading…</SectionShell>;
  if (isError) return <SectionShell title="Default Greeting">Error: {(error as Error).message}</SectionShell>;

  return (
    <SectionShell title="Default Greeting" subtitle="Set the single greeting used for both Hindi and English">
      <div className="space-y-4">
        <p className="text-sm text-onyx/70">This message will be used for callers in both Hindi and English.</p>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={6}
          className="w-full glass-panel rounded-3xl p-5 font-sans text-base text-onyx/80 focus:outline-none focus:ring-2 focus:ring-garnet"
        />
        <div className="flex gap-3 justify-end">
          <button
            onClick={handleReset}
            disabled={deleteMutation.isPending}
            className="px-4 py-2 rounded-full border border-sand-dark/60 text-sm text-onyx/70 hover:border-garnet disabled:opacity-50"
          >
            {deleteMutation.isPending ? "Reverting…" : "Reset to Default"}
          </button>
          <button
            onClick={handleSave}
            disabled={upsertMutation.isPending || !draft.trim()}
            className="px-6 py-2 rounded-full bg-garnet text-white text-sm font-semibold hover:bg-garnet/90 disabled:opacity-50"
          >
            {upsertMutation.isPending ? "Saving…" : "Save Default Greeting"}
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
