import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowUpDown, ExternalLink, FileText } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "./status-badge";
import { ProgressIndicator } from "./progress-indicator";
import { RowActions } from "./row-actions";
import { ReadmeDialog } from "@/components/dialogs/readme-dialog";
import { formatRelativeTime } from "@/lib/utils";
import type { Repository } from "@/lib/types";

function DescriptionCell({ repo }: { repo: Repository }) {
  const [open, setOpen] = useState(false);
  const desc = repo.description;

  if (!desc) return <span className="text-muted-foreground">--</span>;

  const needsTruncation = desc.length > 60;
  const truncated = needsTruncation ? desc.slice(0, 60) + "..." : desc;

  return (
    <>
      <span
        className={`text-muted-foreground ${needsTruncation ? "cursor-pointer hover:text-foreground transition-colors" : ""}`}
        onClick={needsTruncation ? () => setOpen(true) : undefined}
      >
        {truncated}
      </span>
      {needsTruncation && (
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>
                {repo.owner}/{repo.name}
              </DialogTitle>
              <DialogDescription>Repository description</DialogDescription>
            </DialogHeader>
            <p className="text-sm leading-relaxed">{desc}</p>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

function ActionsCell({ repo }: { repo: Repository }) {
  const [readmeOpen, setReadmeOpen] = useState(false);

  return (
    <div className="flex items-center gap-1 justify-end">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        aria-label="View README"
        onClick={() => setReadmeOpen(true)}
      >
        <FileText className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        aria-label="Open on GitHub"
        onClick={() => openUrl(repo.url)}
      >
        <ExternalLink className="h-4 w-4" />
      </Button>
      <RowActions repo={repo} />
      <ReadmeDialog
        repoId={repo.id}
        repoName={`${repo.owner}/${repo.name}`}
        open={readmeOpen}
        onOpenChange={setReadmeOpen}
      />
    </div>
  );
}

export const columns: ColumnDef<Repository>[] = [
  {
    accessorKey: "name",
    header: ({ column }) => (
      <Button
        variant="ghost"
        className="-ml-4"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Repository
        <ArrowUpDown className="ml-2 h-4 w-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const repo = row.original;
      return (
        <div className="font-medium">
          <span className="text-muted-foreground">{repo.owner}/</span>
          {repo.name}
        </div>
      );
    },
    sortingFn: (rowA, rowB) => {
      const a = `${rowA.original.owner}/${rowA.original.name}`.toLowerCase();
      const b = `${rowB.original.owner}/${rowB.original.name}`.toLowerCase();
      return a.localeCompare(b);
    },
  },
  {
    accessorKey: "description",
    header: "Description",
    cell: ({ row }) => <DescriptionCell repo={row.original} />,
  },
  {
    accessorKey: "status",
    header: ({ column }) => (
      <Button
        variant="ghost"
        className="-ml-4"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Status
        <ArrowUpDown className="ml-2 h-4 w-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <div className="space-y-1">
        <StatusBadge status={row.original.status} />
        <ProgressIndicator repoUrl={row.original.url} />
      </div>
    ),
  },
  {
    accessorKey: "last_checked",
    header: ({ column }) => (
      <Button
        variant="ghost"
        className="-ml-4"
        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
      >
        Last Updated
        <ArrowUpDown className="ml-2 h-4 w-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const date = row.original.last_checked;
      if (!date)
        return <span className="text-muted-foreground">Never</span>;
      return (
        <span className="text-muted-foreground">
          {formatRelativeTime(date)}
        </span>
      );
    },
  },
  {
    id: "actions",
    header: "",
    cell: ({ row }) => <ActionsCell repo={row.original} />,
    enableSorting: false,
  },
];
