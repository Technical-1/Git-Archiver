import { Database, Loader2 } from "lucide-react";
import { useRepoStore } from "@/stores/repo-store";
import { useTaskStore } from "@/stores/task-store";

export function StatusBar() {
  const repos = useRepoStore((s) => s.repos);
  const activeTasks = useTaskStore((s) => s.activeTasks);

  const taskCount = activeTasks.size;

  return (
    <footer
      className="flex items-center justify-between border-t bg-muted/50 px-4 py-1 text-xs text-muted-foreground"
      data-testid="status-bar"
    >
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1" data-testid="repo-count">
          <Database className="h-3 w-3" />
          {repos.length} {repos.length === 1 ? "repository" : "repositories"}
        </span>

        {taskCount > 0 && (
          <span
            className="flex items-center gap-1"
            data-testid="active-tasks"
          >
            <Loader2 className="h-3 w-3 animate-spin" />
            {taskCount} active {taskCount === 1 ? "task" : "tasks"}
          </span>
        )}
      </div>

      <span className="text-xs">Git Archiver v2</span>
    </footer>
  );
}
