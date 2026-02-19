import type { ColumnDef } from "@tanstack/react-table";
import { ArrowUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "./status-badge";
import { RowActions } from "./row-actions";
import { formatRelativeTime } from "@/lib/utils";
import type { Repository } from "@/lib/types";

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
    cell: ({ row }) => {
      const desc = row.original.description;
      if (!desc) return <span className="text-muted-foreground">--</span>;
      const truncated = desc.length > 60 ? desc.slice(0, 60) + "..." : desc;
      return (
        <span className="text-muted-foreground" title={desc}>
          {truncated}
        </span>
      );
    },
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
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
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
    cell: ({ row }) => <RowActions repo={row.original} />,
    enableSorting: false,
  },
];
