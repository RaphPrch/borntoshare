// wizard/js/dom.js
export const el = (id) => document.getElementById(id);
export const value = (id) => el(id)?.value?.trim() ?? "";
export const setValue = (id, v) => {
  const e = el(id);
  if (e) e.value = v ?? "";
};
