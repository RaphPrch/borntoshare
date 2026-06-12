export type JobUiStatus =
  | 'never_run'
  | 'queued'
  | 'running'
  | 'success'
  | 'error'
  | 'timeout';

export type JobPollingResult<TPayload = any> = {
  jobId: string;
  status: JobUiStatus;
  payload?: TPayload;
  errorMessage?: string;
};

export type JobPollingOptions<TRawJob = any, TPayload = any> = {
  fetchJob: (jobId: string) => Promise<TRawJob>;
  getRawStatus: (job: TRawJob) => string;
  mapPayload?: (job: TRawJob) => TPayload;
  getErrorMessage?: (job: TRawJob) => string | undefined;
  intervalMs?: number;
  maxAttempts?: number;
  intervalMsByAttempt?: (attempt: number) => number;
  onUpdate?: (status: JobUiStatus, rawJob: TRawJob) => void;
};
