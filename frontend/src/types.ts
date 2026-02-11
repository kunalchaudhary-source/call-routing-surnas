export type GreetingRecord = {
  id: number | null;
  language: string;
  message: string;
  updated_at: string | null;
  is_override: boolean;
};

export type AgentSpecialization = {
  category: string;
  proficiency: number;
};

export type AgentRecord = {
  id: number;
  name: string;
  phone_number: string;
  region: string;
  is_active: boolean;
  is_default: boolean;
  specializations: AgentSpecialization[];
};

export type IVRPromptRecord = {
  id: number | null;
  key: string;
  message: string;
  updated_at: string | null;
  is_override: boolean;
};


export type ApiResponse<T> = T | { status: string };
