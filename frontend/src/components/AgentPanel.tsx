import { FormEvent, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
import { AgentRecord } from "../types";

const categoryPalette: Record<string, string> = {
  necklace: "bg-amber/20 text-amber",
  polki: "bg-garnet/15 text-garnet",
  bridal: "bg-[#b86c6c]/20 text-[#7b2e2e]",
  earrings: "bg-[#778a8c]/15 text-[#3b4a4c]",
  kundan: "bg-[#e6b17c]/20 text-[#5c3614]"
};

type FormState = {
  agentId: number | null;
  name: string;
  countryCode: string;
  localNumber: string;
  region: string;
  specializations: string;
  is_default: boolean;
  is_active: boolean;
};

const initialFormState: FormState = {
  agentId: null,
  name: "",
  countryCode: "",
  localNumber: "",
  region: "IN",
  specializations: "",
  is_default: false,
  is_active: true
};

export function AgentPanel() {
  const { data, isLoading, isError, error } = useQuery<AgentRecord[]>({ queryKey: ["agents"], queryFn: api.listAgents });
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState>(initialFormState);
  const isEditMode = form.agentId !== null;

  const createAgent = useMutation({
    mutationFn: () =>
      api.createAgent({
        name: form.name,
        phone_number: `${form.countryCode}${form.localNumber}`.replace(/\s+/g, ""),
        region: form.region,
        is_default: form.is_default,
        specializations: form.specializations
          .split(",")
          .map((s) => s.trim().toLowerCase())
          .filter(Boolean)
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      setForm(initialFormState);
    }
  });

  const updateAgent = useMutation({
    mutationFn: async () => {
      // Update base agent record
      await api.updateAgent(form.agentId!, {
        name: form.name,
        phone_number: `${form.countryCode}${form.localNumber}`.replace(/\s+/g, ""),
        region: form.region,
        is_default: form.is_default,
        is_active: form.is_active
      });

      // Reconcile specializations: add new ones, remove deleted ones
      const current = (data ?? []).find((a) => a.id === form.agentId);
      const existing = current?.specializations.map((s) => s.category) ?? [];
      const desired = form.specializations
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);

      const toAdd = desired.filter((d) => !existing.includes(d));
      const toRemove = existing.filter((e) => !desired.includes(e));

      await Promise.all(
        toAdd.map((cat) => api.addSpecialization(form.agentId!, { category: cat, proficiency_level: 1 }))
      );
      await Promise.all(
        toRemove.map((cat) => api.removeSpecialization(form.agentId!, cat))
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      setForm(initialFormState);
    }
  });

  const deleteAgent = useMutation({
    mutationFn: (agentId: number) => api.deleteAgent(agentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      if (form.agentId !== null) {
        setForm(initialFormState);
      }
    }
  });

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (isEditMode) {
      updateAgent.mutate();
    } else {
      createAgent.mutate();
    }
  };

  const beginEdit = (agent: AgentRecord) => {
    const raw = agent.phone_number?.trim() ?? "";
    const local = raw.slice(-10);
    const cc = raw.slice(0, Math.max(0, raw.length - 10));
    setForm({
      agentId: agent.id,
      name: agent.name,
      countryCode: cc,
      localNumber: local,
      region: agent.region,
      specializations: agent.specializations.map((s) => s.category).join(", "),
      is_default: agent.is_default,
      is_active: agent.is_active
    });
  };

  const cancelEdit = () => setForm(initialFormState);

  const handleDelete = (agentId: number) => {
    if (confirm("Delete this agent? They will no longer receive calls.")) {
      deleteAgent.mutate(agentId);
    }
  };

  const specialistsByRegion = useMemo(() => {
    return (data ?? []).reduce<Record<string, AgentRecord[]>>((acc, agent) => {
      if (!acc[agent.region]) acc[agent.region] = [];
      acc[agent.region].push(agent);
      return acc;
    }, {});
  }, [data]);

  if (isLoading) {
    return <SectionShell title="Specialist Pools">Loading agents…</SectionShell>;
  }
  if (isError) {
    return <SectionShell title="Specialist Pools">Error: {(error as Error).message}</SectionShell>;
  }

  return (
    <SectionShell title="Specialist Pools" subtitle="Assign experts per region & craft">
      <div className="grid lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          {Object.entries(specialistsByRegion).map(([region, agents]) => (
            <div key={region} className="rounded-2xl border border-sand-dark/40 p-5">
              <header className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.4em] text-amber">{region} pool</p>
                  <p className="text-onyx font-semibold">{agents.length} active specialists</p>
                </div>
                <div className="text-xs text-onyx/60">Default: {agents.find((a) => a.is_default)?.name ?? "None"}</div>
              </header>
              <div className="grid md:grid-cols-2 gap-4">
                {agents.map((agent) => (
                  <article key={agent.id} className="glass-panel rounded-2xl p-4 space-y-3">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-semibold text-onyx">{agent.name}</p>
                        <p className="text-xs text-onyx/60">{agent.phone_number}</p>
                      </div>
                      <div className="flex gap-2 text-xs">
                        <button
                          type="button"
                          onClick={() => beginEdit(agent)}
                          className="px-3 py-1 rounded-full bg-sand/60 text-onyx/70 hover:bg-sand"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(agent.id)}
                          className="px-3 py-1 rounded-full bg-[#fbe4e4] text-[#7b2e2e] hover:bg-[#f8d2d2]"
                          disabled={deleteAgent.isPending}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] uppercase tracking-[0.3em] text-onyx/60">
                      {agent.is_default && <span className="text-garnet">default</span>}
                      <span>{agent.is_active ? "active" : "paused"}</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {agent.specializations.length ? (
                        agent.specializations.map((spec) => (
                          <span
                            key={`${agent.id}-${spec.category}`}
                            className={`text-xs px-3 py-1 rounded-full ${categoryPalette[spec.category] ?? "bg-sand/60 text-onyx/70"}`}
                          >
                            {spec.category} · lvl {spec.proficiency}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-onyx/50">No specializations yet</span>
                      )}
                    </div>
                    <div className="text-[11px] text-onyx/50">Status: {agent.is_active ? "Active" : "Paused"}</div>
                  </article>
                ))}
              </div>
            </div>
          ))}
        </div>
        <form className="glass-panel rounded-2xl p-5 space-y-4" onSubmit={handleSubmit}>
          <header>
            <p className="text-xs uppercase tracking-[0.3em] text-amber">
              {isEditMode ? "Edit specialist" : "Add specialist"}
            </p>
            <p className="text-sm text-onyx/70">
              {isEditMode ? "Update routing details for this concierge" : "Create a concierge and tag their mastery"}
            </p>
          </header>
          <label className="block text-sm text-onyx/70 space-y-2">
            Name
            <input
              required
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full rounded-xl border border-sand-dark/40 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-garnet"
            />
          </label>
          <label className="block text-sm text-onyx/70 space-y-2">
            Phone Number
            <div className="flex gap-2">
              <input
                required
                placeholder="+91"
                value={form.countryCode}
                onChange={(e) => setForm((prev) => ({ ...prev, countryCode: e.target.value }))}
                className="w-24 rounded-xl border border-sand-dark/40 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-garnet"
              />
              <input
                required
                placeholder="10-digit number"
                value={form.localNumber}
                onChange={(e) => setForm((prev) => ({ ...prev, localNumber: e.target.value }))}
                className="flex-1 rounded-xl border border-sand-dark/40 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-garnet"
              />
            </div>
            <p className="text-xs text-onyx/50 mt-1">
              Stored as: {`${form.countryCode}${form.localNumber}`.replace(/\s+/g, "") || "—"}
            </p>
          </label>
          <label className="block text-sm text-onyx/70 space-y-2">
            Region
            <select
              value={form.region}
              onChange={(e) => setForm((prev) => ({ ...prev, region: e.target.value }))}
              className="w-full rounded-xl border border-sand-dark/40 px-3 py-2 bg-white"
            >
              <option value="IN">India / ROW</option>
              <option value="US">US / Canada</option>
              <option value="GLOBAL">Global</option>
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3 text-sm text-onyx/70">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((prev) => ({ ...prev, is_active: e.target.checked }))}
              />
              Active
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm((prev) => ({ ...prev, is_default: e.target.checked }))}
              />
              Default for region
            </label>
          </div>
            <label className="block text-sm text-onyx/70 space-y-2">
              Specializations (comma separated)
              <input
                value={form.specializations}
                onChange={(e) => setForm((prev) => ({ ...prev, specializations: e.target.value }))}
                placeholder="necklace, polki"
                className="w-full rounded-xl border border-sand-dark/40 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-garnet"
              />
            </label>
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={createAgent.isPending || updateAgent.isPending}
              className="flex-1 rounded-full bg-garnet text-white py-2 font-semibold hover:bg-garnet/90 disabled:opacity-50"
            >
              {isEditMode
                ? updateAgent.isPending
                  ? "Saving…"
                  : "Save Changes"
                : createAgent.isPending
                  ? "Creating…"
                  : "Add Specialist"}
            </button>
            {isEditMode && (
              <button
                type="button"
                className="rounded-full border border-sand-dark/40 px-4 py-2 text-sm text-onyx/70"
                onClick={cancelEdit}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
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
