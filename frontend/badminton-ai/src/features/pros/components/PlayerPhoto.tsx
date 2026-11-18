import type { Photo } from "../types";
import { cn } from "@/lib/utils";

type PlayerPhotoProps = {
  photo: Photo | null;
  name: string;
  /** Square edge length in px. */
  size: number;
  className?: string;
};

function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export function PlayerPhoto({ photo, name, size, className }: PlayerPhotoProps) {
  if (!photo) {
    return (
      <div
        role="img"
        aria-label={name}
        style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
        className={cn(
          "flex shrink-0 items-center justify-center rounded-2xl bg-muted font-semibold text-foreground",
          className,
        )}
      >
        {initials(name)}
      </div>
    );
  }

  return (
    <figure className={cn("shrink-0", className)} style={{ width: size }}>
      <img
        src={photo.src}
        alt={`Photo of ${name}`}
        style={{
          width: size,
          height: size,
          objectPosition: `${photo.focusX}% ${photo.focusY}%`,
        }}
        className="rounded-2xl object-cover"
      />
      <figcaption className="mt-1 text-xs text-muted-foreground">{photo.credit}</figcaption>
    </figure>
  );
}
