"use client";

import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Account } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatBytes, formatNumber } from "@/lib/utils";
import { ArrowLeft, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function AccountDetailPage() {
  const params = useParams<{ id: string }>();
  const id = parseInt(params.id, 10);
  const router = useRouter();
  const qc = useQueryClient();

  const { data: account } = useQuery<Account>({
    queryKey: ["account", id],
    queryFn: async () => (await api.get(`/api/accounts/${id}`)).data,
  });

  const rescan = useMutation({
    mutationFn: async () => (await api.post(`/api/accounts/${id}/rescan`)).data,
    onSuccess: (r) => {
      toast.success(`Indexed ${r.indexed_files} files`);
      qc.invalidateQueries({ queryKey: ["account", id] });
    },
  });

  const remove = useMutation({
    mutationFn: async () => (await api.delete(`/api/accounts/${id}`)).data,
    onSuccess: () => {
      toast.success("Account deleted");
      router.push("/accounts");
    },
  });

  if (!account) return <div>Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/accounts")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h2 className="text-2xl font-bold">@{account.username}</h2>
            <p className="text-sm text-muted-foreground">{account.destination_folder}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => rescan.mutate()} disabled={rescan.isPending}>
            <RefreshCw className="h-4 w-4" /> Rescan
          </Button>
          <Button variant="destructive" onClick={() => remove.mutate()}>
            <Trash2 className="h-4 w-4" /> Delete record
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Posts", value: account.total_posts },
          { label: "Stories", value: account.total_stories },
          { label: "Highlights", value: account.total_highlights },
          { label: "Disk size", value: formatBytes(account.total_size_bytes) },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="p-4">
              <div className="text-sm text-muted-foreground">{s.label}</div>
              <div className="text-2xl font-bold">{typeof s.value === "number" ? formatNumber(s.value) : s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Destination folder</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="font-mono text-xs text-muted-foreground break-all">
            {account.destination_folder}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Use Gallery to browse and open files for this account.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
