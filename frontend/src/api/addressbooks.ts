import apiClient from "./client";
import type {
  AddressBook,
  Contact,
  PaginatedResponse,
  DetectedColumn,
  ColumnMapping,
} from "@/types";

export async function listAddressBooks(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<AddressBook>> {
  const response = await apiClient.get<PaginatedResponse<AddressBook>>(
    "/address-books",
    { params }
  );
  return response.data;
}

export async function getAddressBook(id: string): Promise<AddressBook> {
  const response = await apiClient.get<AddressBook>(`/address-books/${id}`);
  return response.data;
}

export async function uploadAddressBook(
  file: File,
  name: string,
  description?: string
): Promise<AddressBook> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("name", name);
  if (description) formData.append("description", description);
  const response = await apiClient.post<AddressBook>(
    "/address-books/upload",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}

export async function getContacts(
  addressBookId: string,
  params?: { page?: number; page_size?: number; search?: string }
): Promise<PaginatedResponse<Contact>> {
  const response = await apiClient.get<PaginatedResponse<Contact>>(
    `/address-books/${addressBookId}/contacts`,
    { params }
  );
  return response.data;
}

export async function detectColumns(
  addressBookId: string
): Promise<DetectedColumn[]> {
  const response = await apiClient.get<DetectedColumn[]>(
    `/address-books/${addressBookId}/detect-columns`
  );
  return response.data;
}

export async function mapColumns(
  addressBookId: string,
  mappings: ColumnMapping[]
): Promise<AddressBook> {
  const response = await apiClient.post<AddressBook>(
    `/address-books/${addressBookId}/map-columns`,
    { mappings }
  );
  return response.data;
}

export async function deleteAddressBook(id: string): Promise<void> {
  await apiClient.delete(`/address-books/${id}`);
}
