import { useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  MoreHorizontal,
  RefreshCw,
  ExternalLink,
  Archive,
  Copy,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ArchiveViewer } from "@/components/dialogs/archive-viewer";
import { useRepoStore } from "@/stores/repo-store";
import { toast } from "@/hooks/use-toast";
import * as commands from "@/lib/commands";
import type { Repository } from "@/lib/types";

interface RowActionsProps {
  repo: Repository;
}

export function RowActions({ repo }: RowActionsProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [removeFiles, setRemoveFiles] = useState(false);
  const [archiveViewerOpen, setArchiveViewerOpen] = useState(false);
  const deleteRepo = useRepoStore((s) => s.deleteRepo);

  const handleUpdate = async () => {
    if (repo.id === null) return;
    try {
      if (repo.status === "pending" || repo.status === "error") {
        await commands.cloneRepo(repo.id);
      } else {
        await commands.updateRepo(repo.id);
      }
      toast({
        title: "Task queued",
        description: `${repo.status === "error" ? "Retry" : "Update"} started for ${repo.owner}/${repo.name}`,
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Error",
        description: String(err),
      });
    }
  };

  const handleOpenOnGitHub = async () => {
    try {
      await openUrl(repo.url);
    } catch {
      toast({
        variant: "destructive",
        title: "Error",
        description: "Failed to open URL in browser",
      });
    }
  };

  const handleCopyUrl = async () => {
    await navigator.clipboard.writeText(repo.url);
    toast({
      title: "Copied",
      description: "Repository URL copied to clipboard",
    });
  };

  const handleDelete = async () => {
    if (repo.id === null) return;
    try {
      await deleteRepo(repo.id, removeFiles);
      toast({
        title: "Deleted",
        description: removeFiles
          ? `Removed ${repo.owner}/${repo.name} and all local files`
          : `Removed ${repo.owner}/${repo.name} from tracking`,
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Error",
        description: String(err),
      });
    }
    setDeleteDialogOpen(false);
    setRemoveFiles(false);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label="Row actions"
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={handleUpdate}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {repo.status === "pending"
              ? "Clone Now"
              : repo.status === "error"
                ? "Retry Clone"
                : "Update Now"}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleOpenOnGitHub}>
            <ExternalLink className="mr-2 h-4 w-4" />
            Open on GitHub
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setArchiveViewerOpen(true)}>
            <Archive className="mr-2 h-4 w-4" />
            View Archives
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleCopyUrl}>
            <Copy className="mr-2 h-4 w-4" />
            Copy URL
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            onClick={() => setDeleteDialogOpen(true)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={deleteDialogOpen} onOpenChange={(open) => {
        setDeleteDialogOpen(open);
        if (!open) setRemoveFiles(false);
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Repository</DialogTitle>
            <DialogDescription>
              Are you sure you want to remove{" "}
              <span className="font-medium">
                {repo.owner}/{repo.name}
              </span>{" "}
              from tracking?
            </DialogDescription>
          </DialogHeader>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={removeFiles}
              onChange={(e) => setRemoveFiles(e.target.checked)}
              className="rounded border-input"
            />
            Also delete cloned files and archives from disk
          </label>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ArchiveViewer
        repo={repo}
        open={archiveViewerOpen}
        onOpenChange={setArchiveViewerOpen}
      />
    </>
  );
}
