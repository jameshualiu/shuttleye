import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type PanelProps = {
  title: string;
  subtitle?: string;
  className?: string;
  children: ReactNode;
};

export function Panel({ title, subtitle, className, children }: PanelProps) {
  return (
    <section className={cn("bg-card text-card-foreground rounded-2xl p-6", className)}>
      <h2 className="text-[18px] font-semibold leading-tight text-foreground">{title}</h2>
      {subtitle && <p className="mt-1 text-[14px] text-muted-foreground">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}
