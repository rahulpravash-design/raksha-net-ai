"use client";

import { useEffect, useState } from "react";

import { formatBytes, formatDateTime, type MediaItem } from "@raksha/api-client";

import { getApiClient } from "@/lib/api";

/**
 * Media is behind authentication, so an `<img src>` pointing at the API would
 * be rejected. Each object is fetched with the bearer token and rendered from
 * an object URL, which is revoked when the gallery unmounts.
 */
export function MediaGallery({ media }: { media: MediaItem[] }) {
  const api = getApiClient();
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const created: string[] = [];

    async function load() {
      for (const item of media) {
        try {
          const url = await api.mediaObjectUrl(item.id);
          created.push(url);
          if (cancelled) return;
          setUrls((previous) => ({ ...previous, [item.id]: url }));
        } catch {
          if (!cancelled) setFailed((previous) => [...previous, item.id]);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
      for (const url of created) URL.revokeObjectURL(url);
    };
  }, [api, media]);

  if (media.length === 0) {
    return <p className="muted text-sm">No photographs were attached.</p>;
  }

  return (
    <ul className="grid grid-cols-2 gap-3">
      {media.map((item) => (
        <li key={item.id} className="space-y-1">
          {urls[item.id] ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={urls[item.id]}
              alt={`Photograph attached to this incident, ${formatDateTime(item.created_at)}`}
              className="aspect-4/3 w-full rounded-lg object-cover"
            />
          ) : (
            <div className="surface flex aspect-4/3 items-center justify-center rounded-lg text-xs muted">
              {failed.includes(item.id) ? "Could not load" : "Loading…"}
            </div>
          )}
          <p className="muted text-xs">{formatBytes(item.size_bytes)}</p>
        </li>
      ))}
    </ul>
  );
}
