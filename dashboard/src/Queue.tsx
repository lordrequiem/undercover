import { useEffect, useState } from "react";
import {
  type CurrentRun,
  type QueueItem,
  fetchCurrentRun,
  fetchQueue,
  formatMoney,
  titleCase,
} from "./api";
import { RunItemBadge, StatusBadge } from "./StatusBadge";

function RunPanel({ run }: Readonly<{ run: CurrentRun }>) {
  return (
    <section className="panel">
      <h2>Current run</h2>
      {run.summary ? (
        <p>{run.summary}</p>
      ) : (
        <p className="muted">Working the queue.</p>
      )}
      <ul className="steps run-items">
        {run.items.map((item) => (
          <li key={item.claim_id}>
            <span className="label claim-id">{item.claim_id}</span>{" "}
            <RunItemBadge status={item.status} />
            {item.note && <div className="detail">{item.note}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Queue() {
  const [claims, setClaims] = useState<QueueItem[] | null>(null);
  const [run, setRun] = useState<CurrentRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    // Keep polling while the page is open, so a run started after the page
    // loads shows up on its own, not only after a reload.
    const load = async () => {
      try {
        const [nextClaims, nextRun] = await Promise.all([
          fetchQueue(),
          fetchCurrentRun(),
        ]);
        if (!active) return;
        setClaims(nextClaims);
        setRun(nextRun);
        setError(null);
      } catch {
        if (active) setError("Could not reach the backend. Retrying.");
      }
      if (active) timer = setTimeout(() => void load(), 1000);
    };
    void load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  if (!claims) return <p className="muted">{error ?? "Loading the queue."}</p>;

  return (
    <>
      {error && <p className="muted">{error}</p>}
      {run && <RunPanel run={run} />}
      <section className="panel">
        <h2>Claims queue</h2>
        <table>
          <thead>
            <tr>
              <th>Claim</th>
              <th>Customer</th>
              <th>Plan</th>
              <th>Type</th>
              <th className="amount">Amount</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((claim) => (
              <tr
                key={claim.claim_id}
                onClick={() =>
                  (window.location.hash = `#/claims/${claim.claim_id}`)
                }
              >
                <td className="claim-id">{claim.claim_id}</td>
                <td>{claim.customer_name}</td>
                <td>{titleCase(claim.plan)}</td>
                <td>{titleCase(claim.claim_type)}</td>
                <td className="amount">{formatMoney(claim.amount_claimed)}</td>
                <td>
                  <StatusBadge state={claim.state} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
