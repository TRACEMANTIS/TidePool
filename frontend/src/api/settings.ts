import apiClient from "./client";
import type {
  SmtpProfile,
  ApiKey,
  User,
  PaginatedResponse,
  GeneralSettings,
} from "@/types";

// -- SMTP Profiles --

export async function listSmtpProfiles(): Promise<SmtpProfile[]> {
  const response = await apiClient.get<SmtpProfile[]>("/settings/smtp");
  return response.data;
}

export async function createSmtpProfile(data: {
  name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  use_tls: boolean;
  from_address: string;
  smtp_type?: string;
}): Promise<SmtpProfile> {
  const response = await apiClient.post<SmtpProfile>("/settings/smtp", data);
  return response.data;
}

export async function updateSmtpProfile(
  id: string,
  data: Partial<{
    name: string;
    host: string;
    port: number;
    username: string;
    password: string;
    use_tls: boolean;
    from_address: string;
    smtp_type: string;
  }>
): Promise<SmtpProfile> {
  const response = await apiClient.patch<SmtpProfile>(
    `/settings/smtp/${id}`,
    data
  );
  return response.data;
}

export async function deleteSmtpProfile(id: string): Promise<void> {
  await apiClient.delete(`/settings/smtp/${id}`);
}

export async function testSmtpProfile(
  id: string,
  testEmail: string
): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post<{
    success: boolean;
    message: string;
  }>(`/settings/smtp/${id}/test`, { email: testEmail });
  return response.data;
}

// -- API Keys --

export async function listApiKeys(): Promise<ApiKey[]> {
  const response = await apiClient.get<ApiKey[]>("/settings/api-keys");
  return response.data;
}

export async function createApiKey(data: {
  name: string;
  expires_in_days?: number;
}): Promise<ApiKey> {
  const response = await apiClient.post<ApiKey>("/settings/api-keys", data);
  return response.data;
}

export async function revokeApiKey(id: string): Promise<void> {
  await apiClient.delete(`/settings/api-keys/${id}`);
}

// -- Users --

export async function listUsers(): Promise<PaginatedResponse<User>> {
  const response = await apiClient.get<PaginatedResponse<User>>(
    "/settings/users"
  );
  return response.data;
}

export async function createUser(data: {
  username: string;
  email: string;
  full_name: string;
  password: string;
  role: "admin" | "operator" | "viewer";
}): Promise<User> {
  const response = await apiClient.post<User>("/settings/users", data);
  return response.data;
}

export async function updateUser(
  id: string,
  data: Partial<{
    email: string;
    full_name: string;
    role: "admin" | "operator" | "viewer";
    is_active: boolean;
  }>
): Promise<User> {
  const response = await apiClient.patch<User>(`/settings/users/${id}`, data);
  return response.data;
}

// -- General Settings --

export async function getGeneralSettings(): Promise<GeneralSettings> {
  const response = await apiClient.get<GeneralSettings>("/settings/general");
  return response.data;
}

export async function updateGeneralSettings(
  data: Partial<GeneralSettings>
): Promise<GeneralSettings> {
  const response = await apiClient.patch<GeneralSettings>(
    "/settings/general",
    data
  );
  return response.data;
}
