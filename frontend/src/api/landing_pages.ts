import apiClient from "./client";
import type {
  LandingPage,
  BuiltinLandingPage,
  PaginatedResponse,
} from "@/types";

export async function listLandingPages(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<LandingPage>> {
  const response = await apiClient.get<PaginatedResponse<LandingPage>>(
    "/landing-pages",
    { params }
  );
  return response.data;
}

export async function getLandingPage(id: string): Promise<LandingPage> {
  const response = await apiClient.get<LandingPage>(`/landing-pages/${id}`);
  return response.data;
}

export async function createLandingPage(data: {
  name: string;
  description?: string;
  html_content: string;
  capture_credentials?: boolean;
  capture_passwords?: boolean;
  redirect_url?: string;
}): Promise<LandingPage> {
  const response = await apiClient.post<LandingPage>("/landing-pages", data);
  return response.data;
}

export async function updateLandingPage(
  id: string,
  data: Partial<{
    name: string;
    description: string;
    html_content: string;
    capture_credentials: boolean;
    capture_passwords: boolean;
    redirect_url: string;
  }>
): Promise<LandingPage> {
  const response = await apiClient.patch<LandingPage>(
    `/landing-pages/${id}`,
    data
  );
  return response.data;
}

export async function deleteLandingPage(id: string): Promise<void> {
  await apiClient.delete(`/landing-pages/${id}`);
}

export async function cloneFromUrl(
  url: string,
  name: string
): Promise<LandingPage> {
  const response = await apiClient.post<LandingPage>(
    "/landing-pages/clone",
    { url, name }
  );
  return response.data;
}

export async function previewLandingPage(
  id: string
): Promise<{ html: string }> {
  const response = await apiClient.get<{ html: string }>(
    `/landing-pages/${id}/preview`
  );
  return response.data;
}

export async function listBuiltinTemplates(): Promise<BuiltinLandingPage[]> {
  const response = await apiClient.get<BuiltinLandingPage[]>(
    "/landing-pages/builtin"
  );
  return response.data;
}

export async function updateLandingPageHtml(
  id: string,
  data: { html: string; css?: string }
): Promise<LandingPage> {
  const response = await apiClient.put<LandingPage>(
    `/landing-pages/${id}/html`,
    data
  );
  return response.data;
}

export async function createFromEditor(data: {
  name: string;
  html: string;
  css: string;
}): Promise<LandingPage> {
  const response = await apiClient.post<LandingPage>(
    "/landing-pages/from-editor",
    data
  );
  return response.data;
}

export async function previewArbitraryHtml(
  html: string
): Promise<{ rendered_html: string }> {
  const response = await apiClient.post<{ rendered_html: string }>(
    "/landing-pages/preview",
    { html }
  );
  return response.data;
}
