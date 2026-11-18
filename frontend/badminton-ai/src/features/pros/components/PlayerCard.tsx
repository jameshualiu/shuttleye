import { Link } from "react-router-dom";
import { PlayerPhoto } from "./PlayerPhoto";
import type { Photo } from "../types";

type PlayerCardProps = {
  to: string;
  name: string;
  photo: Photo | null;
  detail?: string;
  muted?: boolean;
};

export function PlayerCard({ to, name, photo, detail, muted }: PlayerCardProps) {
  return (
    <Link
      to={to}
      className="flex min-h-11 items-center gap-4 rounded-2xl border border-border bg-card p-4 text-card-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <PlayerPhoto photo={photo} name={name} size={56} radius={12} />
      <span className="min-w-0">
        <span className="block font-semibold leading-tight">{name}</span>
        {detail && (
          <span
            className={`mt-0.5 block text-sm ${muted ? "text-muted-foreground" : "text-foreground/80"}`}
          >
            {detail}
          </span>
        )}
      </span>
    </Link>
  );
}
