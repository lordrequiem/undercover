import { useEffect, useState } from "react";
import { type QueueItem, fetchQueue, formatMoney, titleCase } from "./api";
import { StatusBadge } from "./StatusBadge";

export function Queue() {
  const [claims, setClaims] = useState<QueueItem[] | null>(null);

  useEffect(() => {
    void fetchQueue().then(setClaims);
  }, []);

  if (!claims) return <p className="muted">Loading the queue.</p>;

  return (
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
  );
}
