import apiClient from "./client";
import type {
  LiveCampaignStats,
  EventFeedItem,
  SendRatePoint,
  DashboardStats,
} from "@/types";

export async function getDashboardStats(): Promise<DashboardStats> {
  const response = await apiClient.get<DashboardStats>("/monitor/dashboard");
  return response.data;
}

export async function getLiveStats(
  campaignId: string
): Promise<LiveCampaignStats> {
  const response = await apiClient.get<LiveCampaignStats>(
    `/monitor/campaigns/${campaignId}/live`
  );
  return response.data;
}

export async function getEventFeed(params?: {
  limit?: number;
  campaign_id?: string;
  event_type?: string;
}): Promise<EventFeedItem[]> {
  const response = await apiClient.get<EventFeedItem[]>("/monitor/events", {
    params,
  });
  return response.data;
}

export async function getSendRate(
  campaignId: string
): Promise<SendRatePoint[]> {
  const response = await apiClient.get<SendRatePoint[]>(
    `/monitor/campaigns/${campaignId}/send-rate`
  );
  return response.data;
}

export async function getActiveCampaigns(): Promise<LiveCampaignStats[]> {
  const response = await apiClient.get<LiveCampaignStats[]>(
    "/monitor/campaigns/active"
  );
  return response.data;
}
