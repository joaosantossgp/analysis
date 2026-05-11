"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchBatchJobs } from "@/lib/api";
import { type DataLoadState } from "@/lib/update-base-admin";

export type BatchJob = Awaited<ReturnType<typeof fetchBatchJobs>>["items"][number];

type UseBatchJobsResult = {
  batchJobs: BatchJob[];
  jobsState: DataLoadState;
  upsertJob: (job: BatchJob) => void;
};

export function useBatchJobs(): UseBatchJobsResult {
  const [batchJobs, setBatchJobs] = useState<BatchJob[]>([]);
  const [jobsState, setJobsState] = useState<DataLoadState>("loading");

  useEffect(() => {
    let alive = true;
    void fetchBatchJobs()
      .then((payload) => {
        if (!alive) return;
        setBatchJobs(payload.items);
        setJobsState("available");
      })
      .catch(() => {
        if (!alive) return;
        setBatchJobs([]);
        setJobsState("unavailable");
      });

    return () => {
      alive = false;
    };
  }, []);

  const upsertJob = useCallback((job: BatchJob) => {
    setBatchJobs((current) => {
      const next = current.filter((item) => item.job_id !== job.job_id);
      return [job, ...next];
    });
    setJobsState("available");
  }, []);

  return { batchJobs, jobsState, upsertJob };
}
