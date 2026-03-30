import apiClient from "./client";
import type {
  EmailTemplate,
  PretextTemplate,
  PaginatedResponse,
} from "@/types";

export async function listTemplates(params?: {
  page?: number;
  page_size?: number;
  search?: string;
  category?: string;
}): Promise<PaginatedResponse<EmailTemplate>> {
  const response = await apiClient.get<PaginatedResponse<EmailTemplate>>(
    "/templates",
    { params }
  );
  return response.data;
}

export async function getTemplate(id: string): Promise<EmailTemplate> {
  const response = await apiClient.get<EmailTemplate>(`/templates/${id}`);
  return response.data;
}

export async function createTemplate(data: {
  name: string;
  subject: string;
  body_html: string;
  body_text?: string;
  envelope_sender?: string;
  category?: string;
}): Promise<EmailTemplate> {
  const response = await apiClient.post<EmailTemplate>("/templates", data);
  return response.data;
}

export async function updateTemplate(
  id: string,
  data: Partial<{
    name: string;
    subject: string;
    body_html: string;
    body_text: string;
    envelope_sender: string;
    category: string;
  }>
): Promise<EmailTemplate> {
  const response = await apiClient.patch<EmailTemplate>(
    `/templates/${id}`,
    data
  );
  return response.data;
}

export async function deleteTemplate(id: string): Promise<void> {
  await apiClient.delete(`/templates/${id}`);
}

export async function previewTemplate(
  id: string,
  variables?: Record<string, string>
): Promise<{ html: string; subject: string }> {
  const response = await apiClient.post<{ html: string; subject: string }>(
    `/templates/${id}/preview`,
    { variables }
  );
  return response.data;
}

export async function listPretexts(): Promise<PretextTemplate[]> {
  const response = await apiClient.get<PretextTemplate[]>(
    "/templates/pretexts"
  );
  return response.data;
}

export async function getPretext(id: string): Promise<PretextTemplate> {
  const response = await apiClient.get<PretextTemplate>(
    `/templates/pretexts/${id}`
  );
  return response.data;
}
