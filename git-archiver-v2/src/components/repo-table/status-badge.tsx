import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RepoStatus } from "@/lib/types";

const statusConfig: Record<
  RepoStatus,
  { label: string; className: string }
> = {
  active: {
    label: "Active",
    className:
      "bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800",
  },
  pending: {
    label: "Pending",
    className:
      "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800",
  },
  archived: {
    label: "Archived",
    className:
      "bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800",
  },
  deleted: {
    label: "Deleted",
    className:
      "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800",
  },
  error: {
    label: "Error",
    className:
      "bg-destructive/10 text-destructive border-destructive/20 dark:bg-destructive/20 dark:text-red-400 dark:border-destructive/30",
  },
};

interface StatusBadgeProps {
  status: RepoStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status];
  return (
    <Badge
      variant="outline"
      className={cn("text-xs font-medium", config.className)}
    >
      {config.label}
    </Badge>
  );
}
