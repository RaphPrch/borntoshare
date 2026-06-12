import {
  apiDeleteData,
  apiGetList,
  apiPatchData,
  apiPostData,
  type FetchLike
} from "./client";

export type TagOverview = {
  id: number;
  name: string;
  label: string;
  code: string;
  color_rgb?: string | null;
  value_text?: string | null;
};

export type TagWritePayload = {
  name: string;
  label?: string;
  code?: string;
  color_rgb?: string | null;
  color?: string | null;
  value_text?: string | null;
};

export type TagWriteResponse = {
  id: number;
};

export type TagDeleteResponse = {
  ok: boolean;
};

export const listTags = (fetchFn: FetchLike) =>
  apiGetList<TagOverview>(fetchFn, "/tags");

// Existing CRUD (may depend on DAL capabilities)
export const createTag = (fetchFn: FetchLike, payload: TagWritePayload) =>
  apiPostData<TagWriteResponse>(fetchFn, "/tags", payload);
export const updateTag = (fetchFn: FetchLike, id: string | number, payload: TagWritePayload) =>
  apiPatchData<TagWriteResponse>(fetchFn, `/tags/${id}`, payload);
export const deleteTag = (fetchFn: FetchLike, id: string | number) =>
  apiDeleteData<TagDeleteResponse>(fetchFn, `/tags/${id}`);

// Tag attachment for storage endpoints (DAL: /tags/attach + /tags/detach)
export const attachTagToStorageEndpoint = (
  fetchFn: FetchLike,
  payload: { tag_id: number; resource_id: number }
) =>
  apiPostData<{ ok: true }>(fetchFn, "/tags/attach", {
    tag_id: payload.tag_id,
    resource_type: "storage_endpoint",
    resource_id: payload.resource_id
  });

export const detachTagFromStorageEndpoint = (
  fetchFn: FetchLike,
  payload: { tag_id: number; resource_id: number }
) =>
  apiPostData<{ ok: true }>(fetchFn, "/tags/detach", {
    tag_id: payload.tag_id,
    resource_type: "storage_endpoint",
    resource_id: payload.resource_id
  });

export const attachTagToStorageRoot = (
  fetchFn: FetchLike,
  payload: { tag_id: number; resource_id: number }
) =>
  apiPostData<{ ok: true }>(fetchFn, "/tags/attach", {
    tag_id: payload.tag_id,
    resource_type: "storage_root",
    resource_id: payload.resource_id
  });

export const detachTagFromStorageRoot = (
  fetchFn: FetchLike,
  payload: { tag_id: number; resource_id: number }
) =>
  apiPostData<{ ok: true }>(fetchFn, "/tags/detach", {
    tag_id: payload.tag_id,
    resource_type: "storage_root",
    resource_id: payload.resource_id
  });
