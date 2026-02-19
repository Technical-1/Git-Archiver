import { useState, useRef, useEffect } from "react";
import {
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  Info,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useTaskStore } from "@/stores/task-store";
import type { ActivityEntry } from "@/lib/types";

const statusIcons: Record<ActivityEntry["type"], React.ElementType> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

const statusColors: Record<ActivityEntry["type"], string> = {
  success: "text-emerald-600 dark:text-emerald-400",
  error: "text-red-600 dark:text-red-400",
  info: "text-blue-600 dark:text-blue-400",
  warning: "text-amber-600 dark:text-amber-400",
};

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ActivityLog() {
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const activityLog = useTaskStore((s) => s.activityLog);

  // Auto-scroll to top when new entries arrive (newest is first)
  useEffect(() => {
    if (expanded && scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [activityLog.length, expanded]);

  return (
    <div className="border-t bg-background" data-testid="activity-log">
      <Button
        variant="ghost"
        className="w-full flex items-center justify-between px-4 py-2 h-auto rounded-none"
        onClick={() => setExpanded(!expanded)}
        aria-label={expanded ? "Collapse activity log" : "Expand activity log"}
      >
        <span className="text-sm font-medium">
          Activity Log ({activityLog.length})
        </span>
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronUp className="h-4 w-4" />
        )}
      </Button>

      {expanded && (
        <div
          ref={scrollRef}
          className="max-h-48 overflow-y-auto border-t"
          data-testid="activity-log-entries"
        >
          {activityLog.length === 0 ? (
            <p className="text-sm text-muted-foreground p-4 text-center">
              No activity yet.
            </p>
          ) : (
            <ul className="divide-y">
              {activityLog.map((entry) => {
                const Icon = statusIcons[entry.type];
                return (
                  <li
                    key={entry.id}
                    className="flex items-start gap-2 px-4 py-2 text-sm"
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 mt-0.5 shrink-0",
                        statusColors[entry.type],
                      )}
                    />
                    <span className="flex-1">{entry.message}</span>
                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatTimestamp(entry.timestamp)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
