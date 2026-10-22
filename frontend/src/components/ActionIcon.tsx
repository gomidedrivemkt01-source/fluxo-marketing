import { type CSSProperties } from "react";

export function ActionIcon({ src, className = "" }: { src: string; className?: string }) {
  return (
    <span
      className={`action-icon${className ? ` ${className}` : ""}`}
      style={{ "--icon-source": `url("${src}")` } as CSSProperties}
      aria-hidden="true"
    />
  );
}
