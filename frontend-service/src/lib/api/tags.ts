import {
  apiDeleteData,
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

type TagWritePayload = {
  name: string;
  label?: string;
  code?: string;
  color_rgb?: string | null;
  color?: string | null;
  value_text?: string | null;
};

type TagWriteResponse = {
  id: number;
};

type TagDeleteResponse = {
  ok: boolean;
};

// Existing CRUD (may depend on core-service capabilities)
export const createTag = (fetchFn: FetchLike, payload: TagWritePayload) =>
  apiPostData<TagWriteResponse>(fetchFn, "/tags", payload);
export const updateTag = (fetchFn: FetchLike, id: string | number, payload: TagWritePayload) =>
  apiPatchData<TagWriteResponse>(fetchFn, `/tags/${id}`, payload);
export const deleteTag = (fetchFn: FetchLike, id: string | number) =>
  apiDeleteData<TagDeleteResponse>(fetchFn, `/tags/${id}`);

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
