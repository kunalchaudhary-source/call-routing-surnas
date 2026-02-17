import { AgentRecord, GreetingRecord, IVRPromptRecord } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function getAuthHeader() {
  const basic = sessionStorage.getItem("admin_basic") || "";
  return basic ? { Authorization: `Basic ${basic}` } : {};
}

async function fetchWithAuth(input: RequestInfo, init?: RequestInit) {
  const headers = Object.assign({}, init?.headers || {}, getAuthHeader());
  const merged: RequestInit = Object.assign({}, init || {}, { headers });
  return fetch(input, merged);
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const message = await res.text();
    throw new Error(message || `Request failed with ${res.status}`);
  }
  return res.json();
}

export const api = {
  async listGreetings(): Promise<GreetingRecord[]> {
    const res = await fetchWithAuth(`${API_BASE}/admin/greetings`);
    return handle(res);
  },
  async getGreeting(language: string): Promise<GreetingRecord> {
    const res = await fetchWithAuth(`${API_BASE}/admin/greetings/${language}`);
    return handle(res);
  },
  async upsertGreeting(language: string, payload: { message: string }) {
    const res = await fetchWithAuth(`${API_BASE}/admin/greetings/${language}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return handle(res);
  },
  async deleteGreeting(language: string) {
    const res = await fetchWithAuth(`${API_BASE}/admin/greetings/${language}`, {
      method: "DELETE"
    });
    return handle(res);
  },
  async listAgents(): Promise<AgentRecord[]> {
    const res = await fetchWithAuth(`${API_BASE}/admin/agents`);
    return handle(res);
  },
  async createAgent(payload: { name: string; phone_number: string; region: string; is_default?: boolean; specializations: string[] }) {
    const res = await fetchWithAuth(`${API_BASE}/admin/agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return handle(res);
  },
  async updateAgent(agentId: number, payload: Partial<{ name: string; phone_number: string; region: string; is_active: boolean; is_default: boolean }>) {
    const res = await fetchWithAuth(`${API_BASE}/admin/agents/${agentId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return handle(res);
  },
  async deleteAgent(agentId: number) {
    const res = await fetchWithAuth(`${API_BASE}/admin/agents/${agentId}`, {
      method: "DELETE"
    });
    return handle(res);
  },
  async addSpecialization(agentId: number, payload: { category: string; proficiency_level: number }) {
    const res = await fetchWithAuth(`${API_BASE}/admin/agents/${agentId}/specializations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return handle(res);
  },
  async removeSpecialization(agentId: number, category: string) {
    const res = await fetchWithAuth(`${API_BASE}/admin/agents/${agentId}/specializations/${category}`, {
      method: "DELETE"
    });
    return handle(res);
  },
  async listIVRPrompts(): Promise<IVRPromptRecord[]> {
    const res = await fetchWithAuth(`${API_BASE}/admin/ivr-prompts`);
    return handle(res);
  },
  async upsertIVRPrompt(key: string, payload: { message: string }) {
    const res = await fetchWithAuth(`${API_BASE}/admin/ivr-prompts/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return handle(res);
  },
  async deleteIVRPrompt(key: string) {
    const res = await fetchWithAuth(`${API_BASE}/admin/ivr-prompts/${key}`, {
      method: "DELETE"
    });
    return handle(res);
  },
  // Corrections are managed as defaults in the backend; no client CRUD provided.
};
