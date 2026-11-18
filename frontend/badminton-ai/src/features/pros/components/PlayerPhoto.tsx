import type { Photo } from "../types";
import { cn } from "@/lib/utils";

type PlayerPhotoProps = {
  photo: Photo | null;
  name: string;
  /** Square edge length in px. */
  size: number;
  /** Corner radius in px for the image or placeholder. Defaults to 16. */
  radius?: number;
  className?: string;
};

function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export function PlayerPhoto({ photo, name, size, radius = 16, className }: PlayerPhotoProps) {
  if (!photo) {
    return (
      <div
        role="img"
        aria-label={name}
        style={{ width: size, height: size, borderRadius: radius, fontSize: Math.round(size * 0.36) }}
        className={cn(
          "flex shrink-0 items-center justify-center bg-muted font-semibold text-foreground",
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
          borderRadius: radius,
          objectPosition: `${photo.focusX}% ${photo.focusY}%`,
        }}
        className="object-cover"
      />
      <figcaption className="mt-1 text-xs text-muted-foreground">{photo.credit}</figcaption>
    </figure>
  );
}
