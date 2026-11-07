import { useEffect, useState } from "react";
import {
  type ClaimState,
  type CurrentRun,
  type QueueItem,
  fetchCurrentRun,
  fetchQueue,
  formatMoney,
  stateLabel,
  titleCase,
} from "./api";
import { RunItemBadge, StatusBadge } from "./StatusBadge";

const STATE_ORDER: ClaimState[] = [
  "waiting",
  "in_progress",
  "waiting_for_signoff",
  "decided",
  "for_handler",
];

function Overview({ claims }: Readonly<{ claims: QueueItem[] }>) {
  const counts = new Map<ClaimState, number>();
  let totalClaimed = 0;
  for (const claim of claims) {
    counts.set(claim.state, (counts.get(claim.state) ?? 0) + 1);
    totalClaimed += claim.amount_claimed;
  }
  return (
    <section className="panel">
      <h2>Overview</h2>
      <div className="stat-grid">
        <div className="stat">
          <span className="stat-value">{claims.length}</span>
          <span className="stat-label">Total claims</span>
        </div>
        {STATE_ORDER.map((state) => (
          <div className="stat" key={state}>
            <span className="stat-value">{counts.get(state) ?? 0}</span>
            <span className="stat-label">{stateLabel(state)}</span>
          </div>
        ))}
        <div className="stat">
          <span className="stat-value mono">{formatMoney(totalClaimed)}</span>
          <span className="stat-label">Total claimed</span>
        </div>
      </div>
    </section>
  );
}

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
      <Overview claims={claims} />
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
