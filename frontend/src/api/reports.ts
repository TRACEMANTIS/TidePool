import apiClient from "./client";
import type {
  CampaignMetrics,
  DepartmentMetrics,
  ExecutiveSummary,
  TrendData,
  OrgRiskScore,
} from "@/types";

export async function getCampaignMetrics(
  campaignId: string
): Promise<CampaignMetrics> {
  const response = await apiClient.get<CampaignMetrics>(
    `/reports/campaigns/${campaignId}/metrics`
  );
  return response.data;
}

export async function getDepartmentMetrics(
  campaignId?: string
): Promise<DepartmentMetrics[]> {
  const response = await apiClient.get<DepartmentMetrics[]>(
    "/reports/departments",
    { params: campaignId ? { campaign_id: campaignId } : undefined }
  );
  return response.data;
}

export async function getExecutiveSummary(): Promise<ExecutiveSummary> {
  const response = await apiClient.get<ExecutiveSummary>(
    "/reports/executive-summary"
  );
  return response.data;
}

export async function exportPdf(campaignId: string): Promise<Blob> {
  const response = await apiClient.get(
    `/reports/campaigns/${campaignId}/export/pdf`,
    { responseType: "blob" }
  );
  return response.data;
}

export async function exportCsv(campaignId: string): Promise<Blob> {
  const response = await apiClient.get(
    `/reports/campaigns/${campaignId}/export/csv`,
    { responseType: "blob" }
  );
  return response.data;
}

export async function generateCompliancePackage(
  campaignId: string
): Promise<Blob> {
  const response = await apiClient.get(
    `/reports/campaigns/${campaignId}/export/compliance`,
    { responseType: "blob" }
  );
  return response.data;
}

export async function getTrend(): Promise<TrendData[]> {
  const response = await apiClient.get<TrendData[]>("/reports/trend");
  return response.data;
}

export async function getOrgRisk(): Promise<OrgRiskScore> {
  const response = await apiClient.get<OrgRiskScore>("/reports/org-risk");
  return response.data;
}
