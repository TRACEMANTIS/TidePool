import apiClient from "./client";
import type { Campaign, PaginatedResponse } from "@/types";

interface CampaignCreateRequest {
  name: string;
  description: string;
  template_id: string;
  landing_page_id?: string;
  address_book_id: string;
  smtp_profile_id: string;
  scheduled_at?: string;
}

interface CampaignUpdateRequest {
  name?: string;
  description?: string;
  template_id?: string;
  landing_page_id?: string;
  address_book_id?: string;
  smtp_profile_id?: string;
  scheduled_at?: string;
}

interface ListParams {
  page?: number;
  page_size?: number;
  status?: string;
  search?: string;
}

export async function listCampaigns(
  params?: ListParams
): Promise<PaginatedResponse<Campaign>> {
  const response = await apiClient.get<PaginatedResponse<Campaign>>(
    "/campaigns",
    { params }
  );
  return response.data;
}

export async function getCampaign(id: string): Promise<Campaign> {
  const response = await apiClient.get<Campaign>(`/campaigns/${id}`);
  return response.data;
}

export async function createCampaign(
  data: CampaignCreateRequest
): Promise<Campaign> {
  const response = await apiClient.post<Campaign>("/campaigns", data);
  return response.data;
}

export async function updateCampaign(
  id: string,
  data: CampaignUpdateRequest
): Promise<Campaign> {
  const response = await apiClient.patch<Campaign>(`/campaigns/${id}`, data);
  return response.data;
}

export async function startCampaign(id: string): Promise<Campaign> {
  const response = await apiClient.post<Campaign>(`/campaigns/${id}/start`);
  return response.data;
}

export async function pauseCampaign(id: string): Promise<Campaign> {
  const response = await apiClient.post<Campaign>(`/campaigns/${id}/pause`);
  return response.data;
}
