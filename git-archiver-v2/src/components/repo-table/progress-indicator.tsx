import { Loader2 } from "lucide-react";
import { useTaskStore } from "@/stores/task-store";
import type { TaskStage } from "@/lib/types";

const stageLabels: Record<TaskStage, string> = {
  cloning: "Cloning",
  pulling: "Pulling",
  archiving: "Archiving",
  compressing: "Compressing",
  checking_status: "Checking",
};

interface ProgressIndicatorProps {
  repoUrl: string;
}

export function ProgressIndicator({ repoUrl }: ProgressIndicatorProps) {
  const task = useTaskStore((s) => s.activeTasks.get(repoUrl));

  if (!task) return null;

  const label = stageLabels[task.stage];
  const hasProgress = task.progress !== null && task.progress !== undefined;

  return (
    <div
      className="flex items-center gap-1.5 text-xs text-muted-foreground"
      data-testid="progress-indicator"
    >
      <Loader2 className="h-3 w-3 animate-spin" />
      <span>{label}</span>
      {hasProgress && (
        <div className="flex items-center gap-1">
          <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-300"
              style={{ width: `${Math.min(100, task.progress!)}%` }}
              data-testid="progress-bar"
            />
          </div>
          <span className="tabular-nums">{Math.round(task.progress!)}%</span>
        </div>
      )}
    </div>
  );
}
