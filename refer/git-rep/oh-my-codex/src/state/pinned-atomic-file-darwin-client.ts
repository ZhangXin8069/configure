import type { ChildProcessWithoutNullStreams } from 'node:child_process';

const REQUEST_TIMEOUT_MS = 2_000;
const CLOSE_TIMEOUT_MS = 1_000;

type PendingRequest = {
  timer: NodeJS.Timeout;
  resolve: (value: Record<string, unknown>) => void;
  reject: (error: Error) => void;
};

export class JsonChildClient {
  private buffered = '';
  private nextRequestId = 1;
  private pending = new Map<number, PendingRequest>();
  private initialResponse: Record<string, unknown> | null = null;
  private terminalError: Error | null = null;
  private closePromise: Promise<void> | null = null;
  private exited = false;
  private exitDescription = 'unknown';
  private resolveExit!: () => void;
  private readonly exitPromise = new Promise<void>((resolve) => { this.resolveExit = resolve; });

  constructor(
    readonly child: ChildProcessWithoutNullStreams,
    private readonly label: string,
    private readonly onEvent?: (event: Record<string, unknown>) => void,
    private readonly onPendingChange?: (count: number) => void,
  ) {
    child.stderr.resume();
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => this.consume(chunk));
    child.once('error', (error) => this.finish(new Error(`${label} process error`, { cause: error })));
    child.stdin.once('error', (error) => this.finish(new Error(`${label} stdin error`, { cause: error })));
    child.once('exit', (code, signal) => {
      this.exitDescription = String(code ?? signal ?? 'unknown');
    });
    child.once('close', () => {
      this.exited = true;
      this.finish(new Error(`${label} exited (${this.exitDescription})`));
      this.resolveExit();
    });
  }

  private consume(chunk: string): void {
    this.buffered += chunk;
    for (;;) {
      const newline = this.buffered.indexOf('\n');
      if (newline < 0) return;
      const line = this.buffered.slice(0, newline);
      this.buffered = this.buffered.slice(newline + 1);
      let response: Record<string, unknown>;
      try { response = JSON.parse(line) as Record<string, unknown>; }
      catch (error) {
        this.finish(new Error(`${this.label} emitted an invalid response`, { cause: error }));
        this.child.kill('SIGKILL');
        continue;
      }
      const id = response.id;
      const waiter = typeof id === 'number' ? this.pending.get(id) : undefined;
      if (!waiter) {
        if (id === 0 && !this.initialResponse) this.initialResponse = response;
        if (response.event) this.onEvent?.(response);
        continue;
      }
      this.pending.delete(id as number);
      clearTimeout(waiter.timer);
      this.reportPending();
      if (response.ok === true) waiter.resolve(response);
      else waiter.reject(new Error(String(response.error ?? `${this.label} failed`)));
    }
  }

  private reportPending(): void {
    this.onPendingChange?.(this.pending.size);
  }

  private finish(error: Error): void {
    if (!this.terminalError) this.terminalError = error;
    for (const waiter of this.pending.values()) {
      clearTimeout(waiter.timer);
      waiter.reject(this.terminalError);
    }
    this.pending.clear();
    this.reportPending();
  }

  private waitForResponse(id: number, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Record<string, unknown>> {
    if (this.terminalError) return Promise.reject(this.terminalError);
    return new Promise<Record<string, unknown>>((resolve, reject) => {
      const waiter: PendingRequest = {
        resolve,
        reject,
        timer: setTimeout(() => {
          this.pending.delete(id);
          const error = new Error(`${this.label} request timed out`);
          reject(error);
          this.reportPending();
          this.finish(error);
          this.child.kill('SIGKILL');
        }, timeoutMs),
      };
      this.pending.set(id, waiter);
      this.reportPending();
    });
  }

  async initialize(options: { timeoutMs?: number } = {}): Promise<Record<string, unknown>> {
    if (this.initialResponse) {
      const response = this.initialResponse;
      this.initialResponse = null;
      if (response.ok !== true) throw new Error(String(response.error ?? `${this.label} initialization failed`));
      if (response.ready !== true) throw new Error(`${this.label} initialization failed`);
      return response;
    }
    const response = await this.waitForResponse(0, options.timeoutMs);
    if (response.ready !== true) throw new Error(`${this.label} initialization failed`);
    return response;
  }

  request(value: Record<string, unknown>, options: { timeoutMs?: number } = {}): Promise<Record<string, unknown>> {
    const id = this.nextRequestId++;
    const response = this.waitForResponse(id, options.timeoutMs);
    if (this.terminalError) return response;
    this.child.stdin.write(`${JSON.stringify({ id, ...value })}\n`, (error) => {
      if (error) this.finish(new Error(`${this.label} request write failed`, { cause: error }));
    });
    return response;
  }

  isTerminal(): boolean { return this.terminalError !== null; }

  close(): Promise<void> {
    if (this.closePromise) return this.closePromise;
    this.closePromise = this.closeChild();
    return this.closePromise;
  }

  private async closeChild(): Promise<void> {
    let closeError: Error | null = null;
    if (!this.terminalError) {
      try { await this.request({ op: 'close' }); }
      catch (error) { closeError = error instanceof Error ? error : new Error(String(error)); }
    }
    this.child.stdin.end();
    if (this.exited) {
      if (closeError) throw closeError;
      return;
    }
    const exitedGracefully = await Promise.race([
      this.exitPromise.then(() => true),
      new Promise<false>((resolve) => setTimeout(() => resolve(false), CLOSE_TIMEOUT_MS)),
    ]);
    if (exitedGracefully) {
      if (closeError) throw closeError;
      return;
    }
    this.child.kill('SIGKILL');
    await Promise.race([
      this.exitPromise,
      new Promise<void>((resolve) => setTimeout(resolve, CLOSE_TIMEOUT_MS)),
    ]);
    if (closeError) throw closeError;
  }
}

/** Backward-compatible name for the Darwin pinned-file protocol. */
export { JsonChildClient as DarwinJsonChildClient };
