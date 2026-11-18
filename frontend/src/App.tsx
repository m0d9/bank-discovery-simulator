import { useEffect, useState } from 'react';

// M0 placeholder: the only milestone where hard-coded UI text is allowed (i18n arrives in M4).
interface Health {
  status: string;
}

function isHealth(value: unknown): value is Health {
  return (
    typeof value === 'object' &&
    value !== null &&
    'status' in value &&
    typeof value.status === 'string'
  );
}

export default function App() {
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: controller.signal })
      .then((res) => res.json() as Promise<unknown>)
      .then((body) => {
        setStatus(isHealth(body) ? body.status : 'error');
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          console.error(err);
          setStatus('error');
        }
      });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main className="mx-auto max-w-xl ps-6 pe-6 pt-16 text-start">
      <h1 className="text-2xl font-semibold">Bank Client Discovery Simulator</h1>
      <p className="mt-4">
        API health: <strong data-testid="health-status">{status}</strong>
      </p>
    </main>
  );
}
