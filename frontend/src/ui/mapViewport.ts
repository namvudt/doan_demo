type ViewportPoint = {
  id: string;
  latitude: number;
  longitude: number;
};

/** Describe camera intent by coordinates, independently of React object identity. */
export function getMapViewportRequest<T extends ViewportPoint>(
  items: T[],
  selectedId: string | undefined,
  focusSelected: boolean,
) {
  if (!items.length) return null;
  const selected = focusSelected
    ? items.find((item) => item.id === selectedId)
    : undefined;
  if (selected) {
    return {
      key: JSON.stringify([
        "selected",
        selected.id,
        selected.latitude,
        selected.longitude,
      ]),
      selected,
    };
  }
  const coordinates = [
    ...new Set(items.map((item) => `${item.latitude},${item.longitude}`)),
  ].sort();
  return { key: JSON.stringify(["bounds", coordinates]), selected: undefined };
}
