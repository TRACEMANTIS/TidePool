import apiClient from "./client";
import type { AuditLogEntry, PaginatedResponse } from "@/types";

export async function getLogs(params?: {
  page?: number;
  page_size?: number;
  actor?: string;
  action?: string;
  resource_type?: string;
  start_date?: string;
  end_date?: string;
}): Promise<PaginatedResponse<AuditLogEntry>> {
  const response = await apiClient.get<PaginatedResponse<AuditLogEntry>>(
    "/audit/logs",
    { params }
  );
  return response.data;
}

export async function exportLogs(params?: {
  actor?: string;
  action?: string;
  resource_type?: string;
  start_date?: string;
  end_date?: string;
}): Promise<Blob> {
  const response = await apiClient.get("/audit/logs/export", {
    params,
    responseType: "blob",
  });
  return response.data;
}
