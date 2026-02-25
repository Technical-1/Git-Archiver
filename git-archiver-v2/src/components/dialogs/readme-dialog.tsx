import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "@/hooks/use-toast";
import * as commands from "@/lib/commands";

interface ReadmeDialogProps {
  repoId: number | null;
  repoName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReadmeDialog({
  repoId,
  repoName,
  open,
  onOpenChange,
}: ReadmeDialogProps) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || repoId === null) return;
    setLoading(true);
    setContent(null);
    commands
      .getRepoReadme(repoId)
      .then((data) => setContent(data))
      .catch((err) => {
        toast({
          variant: "destructive",
          title: "Failed to load README",
          description: String(err),
        });
      })
      .finally(() => setLoading(false));
  }, [open, repoId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>README: {repoName}</DialogTitle>
          <DialogDescription>From the latest archive</DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto flex-1 min-h-0">
          {loading && (
            <p className="text-sm text-muted-foreground text-center py-8">
              Loading README...
            </p>
          )}
          {!loading && content === null && (
            <p className="text-sm text-muted-foreground text-center py-8">
              No README available. Clone or update the repo first.
            </p>
          )}
          {!loading && content !== null && (
            <div className="prose prose-sm dark:prose-invert max-w-none px-1">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
