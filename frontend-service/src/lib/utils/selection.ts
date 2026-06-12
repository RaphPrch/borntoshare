export const toggleSetValue = <T>(current: Set<T>, value: T, checked?: boolean): Set<T> => {
  const next = new Set(current);
  if (typeof checked === 'boolean') {
    if (checked) next.add(value);
    else next.delete(value);
    return next;
  }
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
};

export const prefixedIdSet = (ids: Array<string | number>, prefix = 'id:'): Set<string> =>
  new Set(
    ids
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0)
      .map((value) => `${prefix}${value}`)
  );

