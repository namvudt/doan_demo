import { useCallback, useEffect, useState } from "react";
import { useApp } from "../app/AppContext";
import type { HeritageView } from "../api/schema";
import type { PreviewHeritage } from "../preview/types";

export type HeritageDisplay = Omit<
  PreviewHeritage,
  "illustrative" | "category"
> & {
  illustrative: boolean;
  category: string;
  coordinateStatus?: "illustrative" | "unverified" | "verified";
};

export function toHeritageDisplay(record: HeritageView): HeritageDisplay {
  return {
    id: record.heritage_id,
    name: record.name,
    slug: record.slug,
    province: record.province,
    address: record.address,
    category: record.category,
    period: record.period,
    introduction: record.summary,
    history: record.historical_information,
    culturalValue: record.cultural_information,
    tags: record.tags,
    coordinates: record.location
      ? {
          latitude: record.location.latitude,
          longitude: record.location.longitude,
          verified: record.location.verification_status === "verified",
          verificationNote: record.location.verification_note,
        }
      : null,
    coordinateStatus: record.location?.verification_status,
    media: record.media.map((media) => ({ ...media, id: media.media_id })),
    sourceIds: record.information_sources.map((source) => source.source_id),
    publicationStatus: record.content_status,
    illustrative: record.illustrative,
    createdAt: record.created_at,
    updatedAt: record.updated_at,
  };
}

export function coordinateLabel(item: HeritageDisplay) {
  if (!item.coordinates) return "Chưa có tọa độ";
  if (item.coordinates.verified) return "Tọa độ đã xác minh";
  return item.coordinateStatus === "unverified"
    ? "Tọa độ chưa xác minh"
    : "Tọa độ minh họa";
}

export function useHeritageCatalog() {
  const app = useApp();
  const supported =
    app.mode === "api" && app.capabilities?.features?.heritage_catalog === true;
  const [records, setRecords] = useState<HeritageView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [revision, setRevision] = useState(0);
  const [offset, setOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState(0);
  useEffect(() => {
    if (!supported) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void app.api
      .heritages({ limit: 500, offset }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setRecords((current) =>
          offset === 0
            ? page.items
            : [
                ...new Map(
                  [...current, ...page.items].map((item) => [
                    item.heritage_id,
                    item,
                  ]),
                ).values(),
              ],
        );
        setTotal(page.total);
        setHasMore(page.has_more);
        setNextOffset(page.offset + page.items.length);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Không tải được catalog di sản.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [app.api, supported, revision, offset]);
  const refresh = useCallback(() => {
    setOffset(0);
    setRevision((value) => value + 1);
  }, []);
  const loadMore = useCallback(() => {
    setOffset(nextOffset);
    setRevision((value) => value + 1);
  }, [nextOffset]);
  return {
    supported,
    records,
    total,
    hasMore,
    loading: supported && loading,
    error,
    refresh,
    loadMore,
  };
}

export function useHeritageRecord(heritageId?: string) {
  const app = useApp();
  const supported =
    app.mode === "api" && app.capabilities?.features?.heritage_catalog === true;
  const [record, setRecord] = useState<HeritageView>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!supported || !heritageId) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setRecord(undefined);
    void app.api
      .heritage(heritageId, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setRecord(next);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Không tải được hồ sơ di sản.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [app.api, supported, heritageId, revision]);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  return {
    supported,
    record: record?.heritage_id === heritageId ? record : undefined,
    loading: supported && loading,
    error,
    refresh,
  };
}
