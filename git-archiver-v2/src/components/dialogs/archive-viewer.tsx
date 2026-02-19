import { useState, useEffect, useCallback } from "react";
import { Download, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/hooks/use-toast";
import { formatFileSize } from "@/lib/utils";
import * as commands from "@/lib/commands";
import type { Repository, ArchiveView } from "@/lib/types";

interface ArchiveViewerProps {
  repo: Repository;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ArchiveViewer({ repo, open, onOpenChange }: ArchiveViewerProps) {
  const [archives, setArchives] = useState<ArchiveView[]>([]);
  const [loading, setLoading] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const fetchArchives = useCallback(async () => {
    if (repo.id === null) return;
    setLoading(true);
    try {
      const data = await commands.listArchives(repo.id);
      setArchives(data);
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to load archives",
        description: String(err),
      });
    } finally {
      setLoading(false);
    }
  }, [repo.id]);

  useEffect(() => {
    if (open) {
      fetchArchives();
    }
  }, [open, fetchArchives]);

  const handleExtract = async (archiveId: number) => {
    // In Tauri, we would use a file dialog to pick a destination.
    // For now, prompt the user for a path using a simple prompt.
    const destDir = window.prompt(
      "Enter destination directory path for extraction:",
    );
    if (!destDir) return;

    try {
      await commands.extractArchive(archiveId, destDir);
      toast({
        title: "Extraction complete",
        description: `Archive extracted to ${destDir}`,
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Extraction failed",
        description: String(err),
      });
    }
  };

  const handleDelete = async (archiveId: number) => {
    try {
      await commands.deleteArchive(archiveId);
      setArchives((prev) => prev.filter((a) => a.id !== archiveId));
      toast({
        title: "Archive deleted",
        description: "The archive has been removed",
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to delete archive",
        description: String(err),
      });
    }
    setDeleteConfirmId(null);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Archives: {repo.owner}/{repo.name}
          </DialogTitle>
          <DialogDescription>
            {archives.length} archive{archives.length !== 1 ? "s" : ""} available
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-80 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <p className="text-sm text-muted-foreground">
                Loading archives...
              </p>
            </div>
          ) : archives.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <p className="text-sm text-muted-foreground">
                No archives found.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Files</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {archives.map((archive) => (
                  <TableRow key={archive.id ?? archive.filename}>
                    <TableCell className="text-sm">
                      {formatDate(archive.created_at)}
                    </TableCell>
                    <TableCell className="text-sm tabular-nums">
                      {formatFileSize(archive.file_size)}
                    </TableCell>
                    <TableCell className="text-sm tabular-nums">
                      {archive.file_count}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className="text-xs"
                      >
                        {archive.is_incremental ? "Incremental" : "Full"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {deleteConfirmId === archive.id ? (
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => handleDelete(archive.id!)}
                          >
                            Confirm
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setDeleteConfirmId(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => handleExtract(archive.id!)}
                            aria-label="Extract archive"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => setDeleteConfirmId(archive.id!)}
                            aria-label="Delete archive"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
